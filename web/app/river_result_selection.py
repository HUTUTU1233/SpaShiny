"""Pure per-analysis selection; no implicit fallback to an older result."""
from dataclasses import dataclass


@dataclass
class RiverResultSelection:
    scope: tuple = ('', '')
    submitted_job_id: str = ''
    selected_job_id: str = ''
    pending_job_id: str = ''
    waiting_for_ui_ack: bool = False
    generation: int = 0

    def reset_scope(self,owner,analysis):
        scope=(str(owner or ''),str(analysis or ''))
        if scope==self.scope:return False
        self.scope=scope
        self.submitted_job_id=self.selected_job_id=self.pending_job_id=''
        self.waiting_for_ui_ack=False;self.generation+=1
        return True

    def submitted(self,job_id):
        if not str(job_id or '').strip():raise ValueError('New submissions require a job_id.')
        self.submitted_job_id=self.pending_job_id=str(job_id)
        self.selected_job_id='';self.waiting_for_ui_ack=True;self.generation+=1

    def succeeded(self,job_id):
        if str(job_id)!=self.submitted_job_id or str(job_id)!=self.pending_job_id:return False
        self.selected_job_id=str(job_id);self.pending_job_id=''
        self.waiting_for_ui_ack=True;self.generation+=1
        return True

    def failed(self,job_id):
        if str(job_id)!=self.pending_job_id:return False
        self.pending_job_id=self.selected_job_id=''
        self.waiting_for_ui_ack=True;self.generation+=1
        return True

    def observe_client(self,job_id,available):
        value=str(job_id or '')
        if self.waiting_for_ui_ack:
            if value==self.selected_job_id:self.waiting_for_ui_ack=False
            return False
        if value and value not in set(map(str,available)):
            raise ValueError('Result not available in this owner/analysis scope.')
        if value==self.selected_job_id:return False
        self.selected_job_id=value;self.generation+=1;return True

    def selected(self,jobs):
        return next((job for job in jobs if str(job.job_id)==self.selected_job_id),None)

    def token(self):return self.scope,self.generation,self.selected_job_id
    def is_current(self,token):return token==self.token()
