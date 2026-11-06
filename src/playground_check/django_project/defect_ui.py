"""Small application cases for defect display, editing, assignment and uploads."""
import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from django.http import HttpResponseRedirect
from playground_check.business_time import local_now
from playground_check.defect_detail_reads import DefectDetailReads
from playground_check.upload_limits import IMAGE_MAX_BYTES, UPLOAD_REQUEST_MAX_BYTES
from . import defect_commands, defect_native
from .defect_forms import DefectFormError, defect_update_payload, defect_edit_context
from .ui_command_adapter import invoke, invoke_upload

LOGGER = logging.getLogger(__name__)


@dataclass
class DefectEditor:
    request: object
    user: dict
    render: Callable
    prefix: str
    connect: Callable
    tid: int = field(init=False)

    @property
    def reads(self):
        return DefectDetailReads(self.connect)

    def dispatch(self):
        try:
            self._validate_request()
        except DefectFormError as exc:
            return self.render('error.html', {'message': str(exc), 'private': True}, status=exc.status)
        return self._post() if self.request.method == 'POST' else self._detail()

    def _validate_request(self):
        if self.request.method == 'POST':
            try:
                length = int(self.request.META.get('CONTENT_LENGTH') or 0)
            except (TypeError, ValueError):
                length = -1
            if length < 0 or length > UPLOAD_REQUEST_MAX_BYTES:
                LOGGER.warning('Defect form rejected: invalid content length (%s)', length)
                raise DefectFormError('Formular ist zu gross oder ungültig.', 413)
        source = self.request.POST if self.request.method == 'POST' else self.request.GET
        try:
            self.tid = int(source.get('tid', ''))
        except (TypeError, ValueError) as exc:
            raise DefectFormError('Ungültige Mangelnummer.') from exc
        if not 0 < self.tid < 2**31:
            raise DefectFormError('Ungültige Mangelnummer.')

    def _failure(self, message, status=400):
        LOGGER.warning('Defect detail form rejected: tid=%s status=%s reason=%s', self.tid, status, message)
        if self.request.method == 'POST' and self.request.POST.get('action') == 'save':
            return self._detail(form_values=self.request.POST, form_error=message, status=status)
        return self.render('error.html', {'message': message, 'private': True, 'user': self.user}, status=status)

    def _post(self):
        if self.request.content_type not in {'application/x-www-form-urlencoded', 'multipart/form-data'}:
            return self._failure('Ungültiger Formularinhalt.')
        if not self.request.FILES and int(self.request.META.get('CONTENT_LENGTH') or 0) > 12_000:
            return self._failure('Formular ist zu gross.', 413)
        action = self.request.POST.get('action')
        try:
            response = self._execute(action)
            return self._action_result(response, action)
        except DefectFormError as exc:
            return self._failure(str(exc), exc.status)
        except (ValueError, TypeError):
            LOGGER.exception('Defect detail input processing failed: tid=%s action=%s', self.tid, action)
            return self._failure('Ungültige Eingabe.')
        except Exception:
            LOGGER.exception('Defect detail action failed')
            return self._failure('Mangel konnte nicht verarbeitet werden.', 503)

    def _execute(self, action):
        if action in {'accept', 'reject'}:
            return self._assign(action)
        if action == 'save':
            return self._save()
        if action == 'mail':
            return invoke(self.request, defect_commands.send_info_mail, {},
                          url=f'/Defect/{self.tid}/send-mail/', kwargs={'tid': self.tid})
        if action in {'photo_before', 'photo_after'}:
            return self._photo(action)
        raise DefectFormError('Ungültige Aktion.')

    def _assign(self, action):
        comment = (self.request.POST.get('comment') or '').strip()
        if len(comment) > 1000:
            raise DefectFormError('Kommentar zu lang.')
        return invoke(self.request, defect_native.assignment_status, {'assignmentComment': comment},
                      url=f'/Defect/{self.tid}/{action}/', kwargs={'tid': self.tid, 'accepted': action == 'accept'})

    def _save(self):
        previous = self.reads.find(self.tid)
        if not previous:
            raise DefectFormError('Mangel nicht gefunden.', 404)
        payload = defect_update_payload(previous, self.request.POST, local_now())
        person_id = payload['responsibleUserFid']
        if person_id > 0 and person_id != previous.get('responsible_user_fid'):
            if not any(row.get('fid') is not None and int(row['fid']) == person_id
                       for row in self.reads.assignable_users()):
                raise DefectFormError('Die ausgewählte Person ist nicht zuweisbar.')
        return invoke(self.request, defect_commands.update_defect, payload, url='/Defect/')

    def _photo(self, action):
        upload = self.request.FILES.get('picture')
        if upload is None or upload.size == 0:
            raise DefectFormError('Bitte ein Bild bis maximal 10 MiB auswählen.')
        if upload.size > IMAGE_MAX_BYTES:
            raise DefectFormError('Bitte ein Bild bis maximal 10 MiB auswählen.', 413)
        signature = upload.read(16)
        upload.seek(0)
        if not signature.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
            raise DefectFormError('Nur JPEG- und PNG-Bilder sind erlaubt.')
        return invoke_upload(self.request, defect_commands.put_defect_picture,
                             {'afterFixing': action == 'photo_after'}, {'picture': upload},
                             method='PUT', url=f'/Defect/Picture/{self.tid}/', kwargs={'tid': self.tid})

    def _action_result(self, response, action):
        if response.status_code == 409:
            return self._failure('Der Mangel wurde zwischenzeitlich geändert. Bitte die Angaben vor dem erneuten Speichern abgleichen.', 409)
        if response.status_code != 200:
            return self._failure('Aktion konnte nicht ausgeführt werden. Berechtigung und Angaben prüfen.', 409)
        try:
            answer = json.loads(response.content)
        except (ValueError, TypeError):
            answer = {}
        if isinstance(answer, dict) and answer.get('errorMessage'):
            return self._failure('Die Änderung wurde abgelehnt. Bitte Angaben und Berechtigung prüfen.', 409)
        return HttpResponseRedirect(self.prefix + f'/defect/?tid={self.tid}&saved={action}')

    def _detail(self, *, form_values=None, form_error='', status=200):
        try:
            row, data, users = self.reads.detail(self.tid)
        except Exception:
            LOGGER.exception('Defect detail lookup failed')
            return self.render('error.html', {'message': 'Mangel derzeit nicht verfügbar.', 'private': True, 'user': self.user}, status=503)
        if not data:
            return self.render('error.html', {'message': 'Mangel nicht gefunden.', 'private': True, 'user': self.user}, status=404)
        context = defect_edit_context(data, users, form_values)
        edited = context['defect']
        context.update(tid=self.tid, form_error=form_error, record_version=row.get('record_version') or '',
                       can_respond=(edited['responsibleUserFid'] == self.user.get('fid') and edited['assignmentStatus'] != 'angenommen'), private=True, user=self.user,
                       saved_action=self.request.GET.get('saved') in {'save', 'mail', 'accept', 'reject', 'photo_before', 'photo_after'})
        return self.render('defect_detail.html', context, status=status)
