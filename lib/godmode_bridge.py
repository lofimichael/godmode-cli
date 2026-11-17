"""Private operation protocol for the native UI; file rules stay in the Python core.

Requests arrive on a private pipe. No operation exports a saved secret. Preview
IDs hold read snapshots in this process and cannot be reused after a write.
"""
import hashlib
import json
import os
import subprocess
import sys


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

    def call(self, request):
        a = self.api
        action = request.get('action')
        if action == 'environment_list':
            rows = a['environment_list'](self.home)
            return {'environments': [dict(name=row['name'], path=row['path'], keys=row['key_count']) for row in rows],
                    'selected': a.get('ACTIVE_ENVIRONMENT', 'default')}
        if action == 'context_list':
            automatic = a['environment_profile'](self.home, a.get('ACTIVE_ENVIRONMENT', 'default'))
            return {'contexts': [dict(name='', profile_path=str(automatic.path))] + a['context_list'](a['profile_home'](self.home)),
                    'selected': a['ACTIVE_CONTEXT'].name if a.get('ACTIVE_CONTEXT') is not None else ''}
        if action in ('environment_select', 'environment_create', 'context_select', 'context_create'):
            name = self._text(request, 'name')
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
                a['ACTIVE_ENVIRONMENT'] = name
            else:
                directory = a['profile_home'](self.home)
                context = (a['context_create'](directory, name) if action == 'context_create'
                           else a['Context'](directory, name) if name else None)
                a['ACTIVE_CONTEXT'] = context
            self.store = a['effective_store'](self.home)
            self.profile = a['business_profile'](self.home)
            self.profile_data = None
            self.keys.clear()
            self.agents.clear()
            return self.call({'action': 'state'})
        if action == 'doctor':
            return a['doctor_report'](self.store, self.profile, a, home=self.home)
        if action == 'state':
            result = {'version': a['VERSION'], 'home': str(self.store.config_dir),
                      'context': a['ACTIVE_CONTEXT'].name if a.get('ACTIVE_CONTEXT') is not None else '',
                      'environment': a.get('ACTIVE_ENVIRONMENT', 'default'),
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
            a['profile_value'](self.profile, self.profile_data, field, value)
            self.profile_data = self.profile.read()
            return {}
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
            plan = self.agents.pop(self._text(request, 'id'), None)
            if plan is None:
                raise ValueError('The agent preview expired. Open Agents again.')
            block, pending, _ = plan
            added = []
            for item in pending:
                if a['add_agent_text'](item['path'], block, item):
                    added.append(a['home_path'](item['path']))
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
