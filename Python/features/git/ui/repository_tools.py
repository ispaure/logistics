"""Feature-owned submodule, subtree, and worktree dialogs.

Uses the workspace job/operation boundary; never starts independent write workers.
"""
from pathlib import Path
from ..repository import Repository
from .dialogs import FormDialog


class RepositoryTools:
    def __init__(self, page):
        self.page = page

    def worktrees_dialog(self):
        path = self.page.path
        def show(entries):
            dialog = FormDialog('Worktrees', self.page, '\n'.join(f'{e.get("worktree", "")} — {e.get("branch", "detached")}' for e in entries))
            operation = dialog.choice('Action', ['Open worktree', 'Add worktree for existing branch'])
            existing = dialog.choice('Existing worktree', [e['worktree'] for e in entries if 'worktree' in e])
            destination = dialog.text('New worktree folder', folder=True)
            occupied = {e.get('branch') for e in entries}
            branch = dialog.choice('Existing unused branch', [r.name[len('refs/heads/'):] for r in self.page.snapshot.refs
                                                              if r.name.startswith('refs/heads/') and r.name not in occupied])
            if dialog.submitted():
                if operation.currentIndex() == 0: self.page.open_repository(existing.currentText())
                else:
                    target, name = destination.text(), branch.currentText()
                    if not target.strip(): self.page._message('Enter a worktree destination.', error=True); return
                    self.page._operation('Add worktree', lambda repo: repo.add_worktree(target, name))
        self.page._job('List worktrees', lambda runner: Repository(path, runner).worktrees(), show)

    def submodules_dialog(self):
        path = self.page.path
        def show(text):
            dialog = FormDialog('Submodules', self.page, text or 'No submodules. Updates check out the commits recorded by the parent repository.')
            operation = dialog.choice('Action', ['Initialize/update recursively', 'Add submodule', 'Open submodule folder'])
            url = dialog.text('URL for new submodule')
            destination = dialog.text('Relative submodule path')
            if dialog.submitted():
                action, address, target = operation.currentIndex(), url.text(), destination.text()
                if action == 0: self.page._operation('Update submodules', lambda repo: repo.update_submodules())
                elif action == 1: self.page._operation('Add submodule', lambda repo: repo.add_submodule(address, target))
                else:
                    candidate = (self.page.path / target).resolve()
                    if not target or not candidate.is_relative_to(self.page.path.resolve()):
                        self.page._message('Choose a submodule path within this repository.', error=True)
                    else: self.page.open_repository(candidate)
        self.page._job('Read submodule status', lambda runner: Repository(path, runner).submodules(), show)

    def subtree_dialog(self):
        path = self.page.path
        def show(result):
            if result.returncode not in (0, 129) or 'git subtree' not in (result.stdout.decode('utf-8', 'replace') + result.stderr):
                self.page._message('git subtree is unavailable in this Git installation.', error=True)
                return
            dialog = FormDialog('Subtrees', self.page, 'Add, pull, or push a repository at a relative directory prefix. Git must have a clean working tree. Successful mappings are remembered locally.')
            saved = self.page.preferences.subtrees.get(str(path), [])
            saved = [v for v in saved if isinstance(v, dict) and all(isinstance(v.get(k), str) for k in ('prefix', 'url', 'branch'))]
            mapping = dialog.choice('Saved mapping', ['New mapping', *(v['prefix'] for v in saved)])
            action = dialog.choice('Action', ['add', 'pull', 'push'])
            prefix = dialog.text('Directory prefix')
            url = dialog.text('Upstream URL')
            branch = dialog.text('Upstream branch', 'main')
            squash = dialog.check('Squash imported history')
            def populate(index):
                if index:
                    value = saved[index - 1]
                    prefix.setText(value['prefix']); url.setText(value['url']); branch.setText(value['branch'])
                    squash.setChecked(bool(value.get('squash')))
            mapping.currentIndexChanged.connect(populate)
            if dialog.submitted():
                operation = action.currentText()
                value = {'prefix': prefix.text(), 'url': url.text(), 'branch': branch.text(), 'squash': squash.isChecked()}
                if operation == 'push' and not self.page._confirm('Push subtree?', f'Publish {value["prefix"]} to {value["url"]}, branch {value["branch"]}?'):
                    return
                def remember(result):
                    self.page.preferences.subtrees[str(path)] = [value, *(v for v in saved if v['prefix'] != value['prefix'])]
                    self.page._save()
                self.page._operation('Subtree ' + operation, lambda repo: repo.subtree(operation, value['prefix'], value['url'], value['branch'], value['squash']), remember)
        self.page._job('Check subtree availability', lambda runner: runner.run(['subtree', '-h'], check=False), show)
