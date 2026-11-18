"""Private operation protocol for the native UI; file rules stay in the Python core.

Requests arrive on a private pipe. No operation exports a saved secret. Preview
IDs hold read snapshots in this process and cannot be reused after a write.
"""
import hashlib
import json
import os
import subprocess
import sys


_PREFERENCES_UNCHANGED = object()
_RECENT_SETUPS_LIMIT = 5


def _ui_settings_file(namespace, home):
    # Reuse the profile writer's ownership, mode, no-symlink, locking and
    # atomic-replace rules for this separate nonsecret file.
    config = namespace['Profile'](namespace['profile_home'](home))
    config.path = config.home / 'ui.json'
    try:
        data = config.read()
    except ValueError as error:
        raise ValueError('Cannot read ui.json. ' + str(error)) from None
    return config, data


def _ui_motion(data):
    if type(data.get('motion', True)) is not bool:
        raise ValueError('ui.json must set motion to true or false. Fix it before changing preferences.')
    return data.get('motion', True)


def _recent_pair(namespace, pair):
    try:
        if (not isinstance(pair, dict) or set(pair) != {'environment', 'context'}
                or not isinstance(pair['environment'], str) or not isinstance(pair['context'], str)):
            raise ValueError()
        namespace['environment_name'](pair['environment'])
        if pair['context'] and namespace['selection_context'](pair['context']) != pair['context']:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('ui.json has invalid recent setups. Each setup needs only valid environment '
                         'and context names.') from None
    return {'environment': pair['environment'], 'context': pair['context']}


def _ui_recent_setups(namespace, data):
    history = data.get('recent_setups', [])
    if not isinstance(history, list) or len(history) > _RECENT_SETUPS_LIMIT:
        raise ValueError('ui.json recent_setups must be a list of at most five setups.')
    result = [_recent_pair(namespace, pair) for pair in history]
    if len({(pair['environment'], pair['context']) for pair in result}) != len(result):
        raise ValueError('ui.json recent_setups must not contain duplicate setups.')
    return result


def _write_ui_settings(config, data):
    try:
        config.write(data)
    except ValueError as error:
        raise ValueError('Could not save ui.json. ' + str(error)) from None


def ui_preferences(namespace, home=None, motion=_PREFERENCES_UNCHANGED):
    """Read or change Motion without opening keys or business profiles."""
    if motion is not _PREFERENCES_UNCHANGED and type(motion) is not bool:
        raise ValueError('Motion must be true or false.')
    config, data = _ui_settings_file(namespace, home)
    current_motion = _ui_motion(data)
    if motion is not _PREFERENCES_UNCHANGED:
        _ui_recent_setups(namespace, data)
        data['motion'] = motion
        _write_ui_settings(config, data)
        current_motion = motion
    return {'motion': current_motion, 'path': str(config.path)}


def record_recent_selection(namespace, home, selected, previous):
    """Record an already-applied pair. Never save active selection or open keys.

    Callers must treat a history error as nonfatal after an active selection save.
    """
    selected, previous = _recent_pair(namespace, selected), _recent_pair(namespace, previous)
    config, data = _ui_settings_file(namespace, home)
    _ui_motion(data)
    history = _ui_recent_setups(namespace, data)
    recent = []
    for pair in [selected, previous] + history:
        if pair not in recent:
            recent.append(pair)
    data['recent_setups'] = recent[:_RECENT_SETUPS_LIMIT]
    _write_ui_settings(config, data)
    return data['recent_setups']


class UIBridge:
    def __init__(self, namespace, home=None):
        self.api, self.home = namespace, home
        self.store = namespace['effective_store'](home)
        self.profile = namespace['business_profile'](home)
        self.profile_data = None
        self.keys, self.agents = {}, {}

    def _id(self):
        return os.urandom(16).hex()

    def _text(self, request, name):
        value = request.get(name)
        if not isinstance(value, str):
            raise ValueError('Invalid UI request.')
        return value

    def _digest(self):
        return hashlib.sha256(self.store._read()[0].encode('utf-8')).hexdigest()

    def _selected_state(self):
        self.store = self.api['effective_store'](self.home)
        self.profile = self.api['business_profile'](self.home)
        self.profile_data = None
        self.keys.clear()
        self.agents.clear()
        return self.call({'action': 'state'})

    def _apply_selection(self, environment, context):
        a = self.api
        previous = {'environment': a.get('ACTIVE_ENVIRONMENT', 'default'),
                    'context': a['ACTIVE_CONTEXT'].name if a.get('ACTIVE_CONTEXT') is not None else ''}
        a['set_active_selection'](self.home, environment, context)
        history_error = None
        try:
            record_recent_selection(a, self.home, {'environment': environment, 'context': context}, previous)
        except (ValueError, OSError) as error:
            detail = str(error) if isinstance(error, ValueError) else 'Check access to ui.json.'
            history_error = 'Active setup saved, but recent setups were not updated. ' + detail
        state = self._selected_state()
        if history_error:
            state['history_error'] = history_error
        return state

    def call(self, request):
        a = self.api
        action = request.get('action')
        if action in ('key_plan', 'key_check', 'key_save', 'profile_save'):
            # A live session pins names, not permission to reconstruct deleted
            # selections. Keep inventory, switching and doctor available.
            if a.get('ACTIVE_ENVIRONMENT', 'default') != 'default' and not self.store.exists():
                raise ValueError('Selected environment is no longer saved. Select another environment, '
                                 'or recreate it with godmode env create NAME.')
            if a.get('ACTIVE_CONTEXT') is not None:
                a['Context'](a['profile_home'](self.home), a['ACTIVE_CONTEXT'].name)
        if action == 'environment_list':
            rows = a['environment_list'](self.home)
            return {'environments': [dict(name=row['name'], path=row['path'], keys=row['key_count']) for row in rows],
                    'selected': a.get('ACTIVE_ENVIRONMENT', 'default')}
        if action == 'context_list':
            automatic = a['environment_profile'](self.home, a.get('ACTIVE_ENVIRONMENT', 'default'))
            selected = a['ACTIVE_CONTEXT'].name if a.get('ACTIVE_CONTEXT') is not None else ''
            return {'contexts': [dict(name='', profile_path=str(automatic.path))]
                                + a['context_list'](a['profile_home'](self.home), missing_selected=selected),
                    'selected': selected}
        if action == 'selection_save':
            environment = a['environment_name'](self._text(request, 'environment'))
            context = self._text(request, 'context')
            if context == '-':
                context = ''
            return self._apply_selection(environment, context)
        if action in ('environment_select', 'environment_create', 'context_select', 'context_create'):
            name = self._text(request, 'name')
            select = request.get('select', True)
            if type(select) is not bool:
                raise ValueError('select must be true or false.')
            if action.startswith('environment_'):
                name = a['environment_name'](name)
                if action == 'environment_create':
                    copy = request.get('copy')
                    if copy is not None and not isinstance(copy, str):
                        raise ValueError('Choose a saved environment to copy.')
                    a['environment_create'](self.home, name, copy_from=copy)
                else:
                    details = a['environment_show'](self.home, name)
                    if name != 'default' and not details['exists']:
                        raise ValueError('Environment is not saved. Create it with godmode env create NAME.')
                environment = name
                context_name = a['ACTIVE_CONTEXT'].name if a.get('ACTIVE_CONTEXT') is not None else ''
            else:
                directory = a['profile_home'](self.home)
                context = (a['context_create'](directory, name) if action == 'context_create'
                           else a['Context'](directory, name) if name else None)
                context_name = context.name if context is not None else ''
                environment = a.get('ACTIVE_ENVIRONMENT', 'default')
            if action.endswith('_create') and not select:
                return self.call({'action': 'state'})
            # Save only after the entire pair validates. The live session changes
            # only after the atomic write succeeds; unrelated open sessions retain
            # their own already-resolved pair.
            return self._apply_selection(environment, context_name)
        if action == 'preferences_save':
            ui_preferences(a, self.home, motion=request.get('motion'))
            return self.call({'action': 'state'})
        if action == 'doctor':
            return a['doctor_report'](self.store, self.profile, a, home=self.home)
        if action == 'state':
            result = {'version': a['VERSION'], 'home': str(self.store.config_dir),
                      'context': a['ACTIVE_CONTEXT'].name if a.get('ACTIVE_CONTEXT') is not None else '',
                      'environment': a.get('ACTIVE_ENVIRONMENT', 'default'),
                      'selection_source': a.get('SELECTION_SOURCE', 'default'),
                      'environment_source': a.get('ACTIVE_SOURCES', {}).get('environment', 'default'),
                      'context_source': a.get('ACTIVE_SOURCES', {}).get('context', 'default'),
                      'startup_sources': dict(a.get('STARTUP_SOURCES', {})),
                      'shell_override': 'GODMODE_ENV' in os.environ or 'GODMODE_CONTEXT' in os.environ,
                      'profile_path': str(self.profile.path),
                      'music_included': a.get('MUSIC_INCLUDED') if a.get('MUSIC_INCLUDED') is not None else self._music_source_exists(),
                      'env_path': str(self.store.env_path), 'providers': a['catalog'](),
                      'fields': [dict(name=name, label=label, description=description)
                                 for name, (label, description) in zip(a['PROFILE_FIELDS'], a['PROFILE_LABELS'])],
                      'intro_seen': a['intro_seen'](self.home), 'store_exists': self.store.exists(),
                      'profile_blurb': a['PROFILE_BLURB'], 'providers_blurb': a['PROVIDERS_BLURB'],
                      'source_url': a['SOURCE_URL'], 'issue_url': a['ISSUE_URL'],
                      'nfo_logo': list(a['NFO_LOGO']),
                      'intro': [text for text, _ in a['INTRO_PAGES'][0][2]]}
            result['preferences'], result['recent_setups'] = {'motion': True}, []
            try:
                _, preferences = _ui_settings_file(a, self.home)
            except ValueError as error:
                result['preferences_error'] = result['history_error'] = str(error)
            else:
                try:
                    result['preferences'] = {'motion': _ui_motion(preferences)}
                except ValueError as error:
                    result['preferences_error'] = str(error)
                try:
                    result['recent_setups'] = _ui_recent_setups(a, preferences)
                except ValueError as error:
                    result['history_error'] = str(error)
            try:
                result['states'] = self.store.states() if self.store.exists() else {}
                base = getattr(self.store, 'store', self.store)
                result['key_count'] = sum(state == 'set' for state in base.states().values())
            except ValueError as error:
                result['states'], result['store_error'], result['key_count'] = {}, str(error), 0
            try:
                self.profile_data = self.profile.read()
                result['profile'] = {key: value for key, value in self.profile_data.items() if key in a['PROFILE_FIELDS']}
            except ValueError as error:
                self.profile_data = None
                result['profile'], result['profile_error'] = {}, str(error)
            state = a['progress'](self.store, self.home)
            state['errors'] = sorted(state['errors'])
            result['progress'] = state
            return result
        if action == 'accept_intro':
            a['mark_intro_seen'](self.home)
            return {}
        if action == 'key_plan':
            name = a['valid_key'](self._text(request, 'name'))
            prompt = a['KeyPrompt'](self.store, a['named'](name), back=True)
            identifier = self._id()
            # One active key field at a time; old candidate snapshots are discarded.
            self.keys = {identifier: {'prompt': prompt, 'digest': self._digest(), 'checked': None}}
            return dict(id=identifier, name=name, title=prompt.title,
                        visit=prompt.key.get('visit', prompt.title), page=prompt.page,
                        steps=prompt.key.get('steps', []), note=prompt.key.get('note', ''),
                        prompt=a['prompt_label'](prompt.key), path=prompt.path,
                        sealed=prompt.sealed, saved=prompt.saved, lines=prompt.plan['lines'])
        if action in ('key_check', 'key_save'):
            record = self.keys.get(self._text(request, 'id'))
            if record is None:
                raise ValueError('The key preview expired. Open the key again.')
            prompt, value = record['prompt'], self._text(request, 'value')
            if len(value.encode('utf-8')) > 1048576:
                raise ValueError('Credential exceeds the 1 MiB limit.')
            pasted = request.get('pasted') is True
            prompt.pasted = pasted or request.get('from_paste') is True
            clean, problem = prompt.check(value)
            candidate = hashlib.sha256(value.encode('utf-8')).hexdigest()
            if action == 'key_check':
                record['checked'] = candidate if clean is not None and not problem else None
                shown = prompt.shown(clean, pasted) if clean is not None else ('sealed(…)' if prompt.sealed else '…')
                return dict(valid=clean is not None and not problem, error=problem or '',
                            masked=prompt.entry(value, clean, pasted),
                            assignment=getattr(prompt, 'saved_name', prompt.name) + '=' + shown,
                            operation='Replace' if prompt.plan['lines'] else 'Add', path=prompt.path,
                            notes=[text for text, _ in prompt.notes(clean, problem, pasted)],
                            command=a['save_command'](getattr(prompt, 'saved_name', prompt.name), shown, prompt.plan, prompt.path))
            if not clean or problem or record['checked'] != candidate:
                raise ValueError('Review the key before saving.')
            self.store.set(prompt.name, clean, expected_digest=record['digest'])
            receipt = 'Saved ' + getattr(prompt, 'saved_name', prompt.name) + '=' + prompt.shown(clean, pasted)
            self.keys.clear()
            prompt.accepted = prompt.imported = None
            return {'receipt': receipt}
        if action == 'profile_save':
            field, value = self._text(request, 'field'), self._text(request, 'value')
            if field not in a['PROFILE_FIELDS'] or self.profile_data is None:
                raise ValueError('Open the profile before editing.')
            changed = a['profile_value'](self.profile, self.profile_data, field, value)
            self.profile_data = self.profile.read()
            return {'changed': changed}
        if action == 'agents_plan':
            block, targets = a['agent_block'](self.home), a['agent_targets']()
            copy_block = a['agent_instruction'](self.home)
            pending, shown = [], []
            for target in targets:
                view = {'name': target['name'], 'path': a['home_path'](target['path']),
                        'added': target['added'], 'created': False, 'addition': ''}
                if not target['added']:
                    try:
                        plan = a['agent_plan'](target['path'], block)
                        plan['display_path'] = view['path']
                        pending.append(plan)
                        view.update(created=plan['created'], addition=plan['addition'].decode('utf-8'),
                                    real=a['home_path'](plan['real']))
                    except (ValueError, OSError) as error:
                        view['issue'] = str(error) if isinstance(error, ValueError) else 'Cannot read this file.'
                shown.append(view)
            identifier = self._id()
            self.agents = {identifier: (block, pending, copy_block)}
            return dict(id=identifier, block=block, copy_block=copy_block, targets=shown,
                        added_lines=sum(plan['addition'].count(b'\n') for plan in pending), removed_lines=0,
                        can_copy=bool(a['clipboard']()))
        if action == 'copy_agent':
            plan = self.agents.get(self._text(request, 'id'))
            if plan is None:
                raise ValueError('The agent preview expired. Open Agents again.')
            copier = a['clipboard']()
            if not copier:
                return {'copied': False}
            try:
                subprocess.run(copier, input=plan[2].encode('utf-8'), timeout=5, check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                return {'copied': False}
            return {'copied': True}
        if action == 'agents_apply':
            identifier = self._text(request, 'id')
            plan = self.agents.get(identifier)
            if plan is None:
                raise ValueError('The agent preview expired. Open Agents again.')
            block, pending, _ = plan
            if 'targets' in request:
                selected = request['targets']
                if (not isinstance(selected, list) or not selected
                        or any(not isinstance(path, str) for path in selected)
                        or len(set(selected)) != len(selected)
                        or not set(selected).issubset(item['display_path'] for item in pending)):
                    raise ValueError('Choose one or more distinct targets from the reviewed agent preview.')
                # Filter the server-held snapshots, never construct a path from
                # user input. Invalid selections leave the preview reusable.
                pending = [item for item in pending if item['display_path'] in selected]
            self.agents.pop(identifier)
            added = []
            for item in pending:
                if a['add_agent_text'](item['path'], block, item):
                    added.append(item['display_path'])
            return {'added': added}
        if action == 'mark_agent':
            a['mark'](self.home, a['AGENT_MARKER'])
            return {}
        if action == 'faq':
            return {'entries': [dict(title=title, paragraphs=paragraphs)
                                for title, paragraphs in a['faq_entries'](self.home)]}
        if action == 'open_url':
            return {'opened': a['open_page'](self._text(request, 'url'))}
        raise ValueError('Unknown UI operation.')

    def _music_source_exists(self):
        # Modular development has a neighboring adapter; assembled builds use globals.
        module_file = self.api.get('__file__')
        if not module_file:
            return False
        from pathlib import Path
        return (Path(module_file).parent / 'lib' / 'godmode_music.py').is_file()


def ui_bridge(home=None, namespace=None):
    bridge = UIBridge(namespace, home)
    while True:
        raw = sys.stdin.buffer.readline(8 * 1024 * 1024 + 1)
        if not raw:
            return 0
        if len(raw) > 8 * 1024 * 1024 or not raw.endswith(b'\n'):
            return 2  # Never let a fragment become a second operation.
        try:
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise ValueError('Invalid UI request.')
            result = {'ok': True, 'data': bridge.call(request)}
        except (ValueError, UnicodeError) as error:
            # JSON decoding errors can include submitted input in their string.
            result = {'ok': False, 'error': 'Invalid UI request.' if isinstance(error, json.JSONDecodeError) else str(error)}
        except OSError:
            result = {'ok': False, 'error': 'The local file operation failed. Check file access.'}
        except Exception:
            result = {'ok': False, 'error': 'The local operation failed.'}
        raw = None
        sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(',', ':')) + '\n')
        sys.stdout.flush()


def ui_startup_error(message):
    """Complete one bounded handshake when selection fails before bridge creation.

    No stderr/traceback capture and no request content enters the response.
    """
    raw = sys.stdin.buffer.readline(8 * 1024 * 1024 + 1)
    if not raw or len(raw) > 8 * 1024 * 1024 or not raw.endswith(b'\n'):
        return 2
    try:
        if not isinstance(json.loads(raw), dict):
            raise ValueError()
    except (ValueError, UnicodeError):
        message = 'Invalid UI request.'
    safe = ''.join(' ' if ord(char) < 32 or 127 <= ord(char) < 160 else char for char in message)[:1024]
    sys.stdout.write(json.dumps({'ok': False, 'error': safe}, ensure_ascii=True, separators=(',', ':')) + '\n')
    sys.stdout.flush()
    return 2
