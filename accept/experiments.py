from __future__ import print_function
from __future__ import division
import os
import logging
from . import core

APPSDIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'apps')
OPT_KINDS = {
    'loopperf': ('loop',),
    'desync':   ('lock', 'barrier'),
    'aarelax':  ('alias',),
}

def dump_config(config, descs):
    """Given a relaxation configuration and an accompanying description
    map, returning a human-readable string describing it.
    """
    optimizations = [r for r in config if r[1]]
    if not optimizations:
        return u'no optimizations'

    out = []
    for ident, param in optimizations:
        out.append(u'{} @ {}'.format(descs[ident], param))
    return u', '.join(out)

def dump_results_human(results, descs, pout, verbose):
    """Generate human-readable text (as a sequence of lines) for
    the results.
    """
    optimal, suboptimal, bad = core.triage_results(results)

    if verbose and isinstance(pout, str):
        yield 'precise output: {}'.format(pout)
        yield ''

    yield '{} optimal, {} suboptimal, {} bad'.format(
        len(optimal), len(suboptimal), len(bad)
    )
    for res in optimal:
        yield dump_config(res.config, descs)
        yield '{:.1%} error'.format(res.error)
        yield '{} speedup'.format(res.speedup)
        if verbose and isinstance(res.output, str):
            yield 'output: {}'.format(res.output)

    if verbose:
        yield '\nsuboptimal configs:'
        for res in suboptimal:
            yield dump_config(res.config, descs)
            yield '{:.1%} error'.format(res.error)
            yield '{} speedup'.format(res.speedup)

        yield '\nbad configs:'
        for res in bad:
            yield dump_config(res.config, descs)
            yield res.desc

def dump_results_json(results, descs):
    """Return a JSON-like representation of the results.
    """
    results, _, _ = core.triage_results(results)
    out = []
    for res in results:
        out.append({
            'config': dump_config(res.config, descs),
            'error': res.error,
            'speedup_mu': res.speedup.value,
            'speedup_sigma': res.speedup.error,
        })
    return out

def run_experiments(ev):
    """Run all stages in the Evaluation for producing paper-ready
    results. Returns the main results and a dict of kind-restricted
    results.
    """
    ev.setup()

    # Main results.
    base_results = ev.evaluate_base()
    tuned_results = ev.parameter_search(base_results)
    composite_results = ev.evaluate_composites(tuned_results)
    main_results = set(base_results + tuned_results + composite_results)

    # Experiments with only one optimization type at a time.
    kind_results = {}
    for kind, words in OPT_KINDS.items():
        # Filter all base configs for configs of this kind.
        logging.info('evaluating {} in isolation'.format(kind))
        kind_configs = []
        for config in core.permute_config(ev.base_config):
            for ident, param in config:
                if param and not ev.descs[ident].startswith(words):
                    break
            else:
                kind_configs.append(config)

        # Run the experiment workflow.
        logging.info('isolated configs: {}'.format(len(kind_configs)))
        base_results = ev.run_approx(kind_configs)
        tuned_results = ev.parameter_search(base_results)
        composite_results = ev.evaluate_composites(tuned_results)
        kind_results[kind] = set(base_results + tuned_results +
                                 composite_results)

    return main_results, kind_results

def evaluate(client, appname, verbose=False, reps=1, as_json=False):
    appdir = os.path.join(APPSDIR, appname)
    exp = core.Evaluation(appdir, client, reps)
    
    setup_script = os.path.join(appdir, 'setup.sh')
    if os.path.exists(setup_script):
        logging.info('running setup script')
        with core.chdir(appdir):
            core.run_cmd(['sh', 'setup.sh'])

    logging.info('starting experiments')
    with client:
        main_results, kind_results = run_experiments(exp)
    logging.info('all experiments finished')

    if as_json:
        return dump_results_json(main_results, exp.descs)
    else:
        return '\n'.join(
            dump_results_human(main_results, exp.descs, exp.pout, verbose)
        )
