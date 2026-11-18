"""A saved default pair; command and shell selections remain process-local."""
import os
from pathlib import Path

from godmode_context import Context, context_name
from godmode_environment import environment_profile
from godmode_profile import Profile, ProfileDirectoryError
from godmode_store import Store, environment_name


def selection_home(home=None):
    selected = home or os.environ.get('GODMODE_HOME') or os.environ.get('GODMODE_CONFIG_DIR')
    return Path(os.path.abspath(os.path.expanduser(str(selected or Path.home() / '.godmode'))))


def selection_context(name):
    """'-' explicitly uses the environment's profile; every old context name stays valid."""
    return '' if name == '-' else context_name(name)


def selection_saved(home=None):
    config = Profile(selection_home(home), filename='active.json')
    try:
        data = config.read()
    except ProfileDirectoryError:
        raise
    except ValueError as error:
        raise ValueError('Cannot read active.json. Repair the active selection file, or select both '
                         '--env NAME and --context NAME (--context - uses the environment profile). '
                         + str(error)) from None
    if not data and not os.path.lexists(config.path):
        return {'environment': 'default', 'context': ''}, False
    try:
        if (set(data) != {'schema', 'environment', 'context'} or type(data['schema']) is not int
                or data['schema'] != 1 or not isinstance(data['context'], str)):
            raise ValueError('Invalid selection.')
        environment_name(data['environment'])
        if data['context']:
            context_name(data['context'])
    except (ValueError, TypeError, KeyError):
        raise ValueError('active.json has an invalid selection. Select both --env NAME and '
                         '--context NAME, then use godmode use to save a valid pair.') from None
    return {'environment': data['environment'], 'context': data['context']}, True


def selection_resolve(home=None, environment=None, context=None, environ=None):
    """Resolve once. Explicit overrides can recover an invalid saved selection."""
    environ = os.environ if environ is None else environ
    values, sources = {}, {}
    for name, explicit, variable in (('environment', environment, 'GODMODE_ENV'),
                                      ('context', context, 'GODMODE_CONTEXT')):
        if explicit is not None:
            values[name], sources[name] = explicit, 'command'
        elif variable in environ:
            values[name], sources[name] = environ[variable], 'shell'
    if len(values) < 2:
        saved, exists = selection_saved(home)
        for name in ('environment', 'context'):
            if name not in values:
                values[name], sources[name] = saved[name], 'saved' if exists else 'default'
    values['environment'] = environment_name(values['environment'])
    # Saved automatic is ''; an explicitly empty option is a mistake, never a reset.
    if sources['context'] in ('command', 'shell'):
        values['context'] = selection_context(values['context'])
    elif values['context']:
        values['context'] = context_name(values['context'])
    values['sources'] = sources
    values['selection_source'] = next(iter(set(sources.values()))) if len(set(sources.values())) == 1 else 'mixed'
    return values


def selection_validate(home, environment, context):
    """Read only selected paths/metadata; no unsealing and no fallback to another file."""
    environment = environment_name(environment)
    store = Store(home, environment=environment)
    if environment != 'default' and not store.exists():
        raise ValueError('Selected environment is not saved. Create it with godmode env create '
                         + environment + ', or switch with godmode use --env default --context -.')
    # The existing readers verify ownership, modes, symlinks and file syntax.
    store.states()
    selected_context = Context(selection_home(home), context) if context else None
    profile = selected_context.profile() if selected_context else environment_profile(home, environment)
    profile.read()
    return selected_context


def selection_save(home, environment, context):
    """Save the whole reviewed pair atomically, preserving all credential/profile files."""
    environment = environment_name(environment)
    if context:
        context = context_name(context)
    selected_context = selection_validate(home, environment, context)
    config = Profile(selection_home(home), filename='active.json')
    try:
        config.read()
        config.write({'schema': 1, 'environment': environment, 'context': context})
    except ValueError as error:
        raise ValueError('Could not save active.json. ' + str(error)) from None
    return selected_context
