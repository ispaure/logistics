"""Git job ownership, completion, refresh scheduling and cooperative shutdown.

RepositoryView supplies presentation methods; repository commands retain domain policy.
"""
from .worker import GitWorker
from ..repository import Repository
from ..runner import CommandResult


class GitJobs:
    def _job(self, label, action, after=None, *, refresh=False):
        if self.busy or self.closing: return False
        self._message(label + '…')
        self._append_log('\n' + label + '\n')
        self._set_busy(True)
        worker = GitWorker(self.preferences.executable, action, self)
        from ..options import git_defaults
        options = self.preferences.options
        worker.runner.config_options = git_defaults(options)
        worker.runner.diff_limit = options['diff_limit_kb'] * 1024
        for key in ('author_date', 'keep_backups', 'no_ff', 'check_submodules', 'push_tags'):
            setattr(worker.runner, key, options[key])
        self.worker = worker
        worker.progress.connect(self._append_log)
        worker.finished.connect(lambda: self._finished(worker, label, after, refresh))
        worker.start()
        if options['full_output']: self.log_toggle.setChecked(True)
        return True

    def _finished(self, worker, label, after, refresh):
        self.worker = None
        self._set_busy(False)
        error = worker.error
        result = worker.result
        worker.deleteLater()
        if self.closing:
            self.idle.emit()
            return
        if error:
            self._message(error, error=not worker.cancelled)
            self._append_log(error + '\n')
            self.log_toggle.setChecked(True)
        else:
            self._message(label + ' completed.')
            if isinstance(result, CommandResult) and result.stdout:
                self._append_log(result.stdout[-65536:].decode('utf-8', 'replace') + '\n')
            if after:
                try: after(result)
                except (OSError, ValueError) as exc: self._message(str(exc), error=True)
        if (refresh or self._refresh_pending) and self.path and not self.busy:
            # Refresh even after failure: merge conflicts and cancellation can
            # leave valid new repository state. Keep the operation error visible.
            self._refresh_pending = False
            self._refresh(error)
        if not self.busy:
            if getattr(self, '_search_pending', False):
                self._search_pending = False
                self.search_history()
            if not self.busy:
                if getattr(self, '_focus_search_pending', False):
                    self._focus_search_pending = False
                    self.search_results.search.setFocus()
                self.idle.emit()

    def _operation(self, label, action, after=None):
        if self.path is None: return
        path = self.path
        return self._job(label, lambda runner: action(Repository(path, runner)), after, refresh=True)

    def cancel(self):
        if self.worker:
            self.worker.cancel()
            self._message('Cancellation requested…')

    def prepare_close(self):
        self.closing = True
        if self.worker:
            self.cancel()
            return False
        return True

