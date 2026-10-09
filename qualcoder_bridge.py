# noScribeEdit 
# Part of noScribe, the AI-powered Audio Transcription
# Copyright (C) 2025 Kai Dröge
# ported to MAC by Philipp Schneider (gernophil)
# Based on Megasolid Idiom - https://www.pythonguis.com/examples/python-rich-text-editor/

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import json
import os
import re
import socket
import urllib.error
import urllib.request

import AdvancedHTMLParser
from PyQt6 import QtCore, QtWidgets

DEFAULT_ENDPOINT = "http://127.0.0.1:47363/mcp"
CONFIG_ENDPOINT_KEY = "qualcoder_mcp_endpoint"
CONFIG_TIMESTAMPS_KEY = "qualcoder_timestamps"
TIMESTAMP_CHOICES = (
    ("paragraph", "At the start of each paragraph (speaker turn)"),
    ("segment", "At the start of every segment"),
    ("none", "No timestamps"),
)
TOOL_CREATE_DOCUMENT = "documents_create_text_document"
TOOL_PROJECT_STATUS = "project_get_status"


class QualCoderMcpError(Exception):
    """Error reported by QualCoder or by the connection to it."""


def _ms_to_timestamp(milliseconds: int) -> str:
    hours, rest = divmod(int(milliseconds), 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds = rest // 1000
    return f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"


def _segment_start_ms(anchor) -> int | None:
    """Return the start time of a noScribe segment anchor (href or name 'ts_START_STOP...')."""
    for attribute in ("href", "name"):
        value = anchor.getAttribute(attribute)
        if value and str(value).startswith("ts_"):
            parts = str(value).split("_")
            if len(parts) >= 3 and parts[1].isdigit():
                return int(parts[1])
    return None


def transcript_to_text(html_str: str, html_node_to_text, timestamps: str = "paragraph") -> str:
    """Convert the editor HTML to plain text, optionally prefixing [hh:mm:ss] stamps QualCoder can sync to audio.

    html_node_to_text is the editor's own converter, so the text matches its .txt export.
    """
    parser = AdvancedHTMLParser.AdvancedHTMLParser()
    parser.parseStr(html_str)
    if timestamps == "segment":
        for anchor in parser.getElementsByTagName("a"):
            start = _segment_start_ms(anchor)
            if start is None:
                continue
            first_child = anchor.childBlocks[0] if anchor.childBlocks else None
            anchor.insertBefore(" " + _ms_to_timestamp(start) + " ", first_child)
    elif timestamps == "paragraph":
        for paragraph in parser.getElementsByTagName("p"):
            anchors = [node for node in paragraph.getAllChildNodes() if node.tagName.lower() == "a"]
            starts = [s for s in (_segment_start_ms(a) for a in anchors) if s is not None]
            if not starts:
                continue
            first_child = paragraph.childBlocks[0] if paragraph.childBlocks else None
            paragraph.insertBefore(_ms_to_timestamp(min(starts)) + " ", first_child)
    text = html_node_to_text(parser.body) if parser.body is not None else ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Single spaces around inserted stamps, none at line start
    text = re.sub(r"[ \t]*(\[\d\d:\d\d:\d\d\])[ \t]*", r" \1 ", text)
    text = re.sub(r"(?m)^[ \t]+", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


class QualCoderMcpClient:
    """Minimal MCP client over Streamable HTTP, stdlib only; QualCoder's listener is stateless."""

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 90.0):
        self.endpoint = endpoint.strip() or DEFAULT_ENDPOINT
        self.timeout = timeout
        self._next_id = 1

    def _post(self, method: str, params: dict) -> dict:
        request_id = self._next_id
        self._next_id += 1
        body = json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
                "User-Agent": "noScribeEdit",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")[:300]
            raise QualCoderMcpError(f"QualCoder answered HTTP {err.code}.\n{detail}") from err
        except urllib.error.URLError as err:
            reason = err.reason
            if isinstance(reason, (ConnectionRefusedError, socket.timeout, TimeoutError, OSError)):
                raise QualCoderMcpError(
                    f"Could not reach QualCoder at {self.endpoint}.\n\n"
                    "Make sure QualCoder is running, a project is open, and the external MCP server "
                    "is enabled in QualCoder's Settings (AI section)."
                ) from err
            raise QualCoderMcpError(f"Connection error: {reason}") from err
        except (socket.timeout, TimeoutError) as err:
            raise QualCoderMcpError("QualCoder did not answer in time.") from err

        message = self._parse_response(raw, content_type, request_id)
        if "error" in message:
            error = message["error"]
            raise QualCoderMcpError(str(error.get("message", error)) if isinstance(error, dict) else str(error))
        result = message.get("result")
        if not isinstance(result, dict):
            raise QualCoderMcpError("Unexpected answer from QualCoder (no result).")
        return result

    @staticmethod
    def _parse_response(raw: str, content_type: str, request_id: int) -> dict:
        """Accept a plain JSON body or an SSE stream and return the message answering request_id."""
        candidates = []
        if "text/event-stream" in content_type:
            data_lines = []
            for line in raw.splitlines() + [""]:
                if line.startswith("data:"):
                    data_lines.append(line[5:].strip())
                elif line == "" and data_lines:
                    candidates.append("\n".join(data_lines))
                    data_lines = []
        else:
            candidates.append(raw)
        last_message = None
        for candidate in candidates:
            try:
                message = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                last_message = message
                if message.get("id") == request_id:
                    return message
        if last_message is None:
            raise QualCoderMcpError("Unexpected answer from QualCoder (not JSON-RPC).")
        return last_message

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Call one QualCoder tool and return its structured payload."""
        result = self._post("tools/call", {"name": name, "arguments": arguments})
        texts = [
            item.get("text", "") for item in result.get("content", [])
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        payload = result.get("structuredContent")
        if result.get("isError"):
            # QualCoder puts the readable reason in structuredContent.error, the text is only a summary
            error = payload.get("error") if isinstance(payload, dict) else None
            message = str(error.get("message", "")) if isinstance(error, dict) else ""
            raise QualCoderMcpError(message or "\n".join(t for t in texts if t) or "QualCoder rejected the request.")
        if isinstance(payload, dict):
            return payload
        for text in texts:
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, dict):
                return parsed
        return {"text": "\n".join(texts)}

    def project_status(self) -> dict:
        return self.call_tool(TOOL_PROJECT_STATUS, {})

    def create_text_document(self, name: str, text: str, memo: str = "", rename_if_exists: bool = False) -> dict:
        arguments = {"name": name, "text": text, "memo": memo}
        if rename_if_exists:
            arguments["rename_if_exists"] = True
        return self.call_tool(TOOL_CREATE_DOCUMENT, arguments)


class _RequestWorker(QtCore.QThread):
    """Run one blocking MCP call off the GUI thread."""

    succeeded = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self._func = func

    def run(self):
        try:
            self.succeeded.emit(self._func())
        except QualCoderMcpError as err:
            self.failed.emit(str(err))
        except Exception as err:
            self.failed.emit(f"{type(err).__name__}: {err}")


class SendToQualCoderDialog(QtWidgets.QDialog):
    """Ask for name, timestamps and memo, then create the document in the open QualCoder project."""

    def __init__(self, parent, html_str: str, html_node_to_text, config: dict,
                 transcript_path: str | None, audio_source: str | None):
        super().__init__(parent)
        self.setWindowTitle("Send transcript to QualCoder")
        self.setMinimumWidth(560)
        self._html_str = html_str
        self._html_node_to_text = html_node_to_text
        self._config = config
        self._worker = None
        self.result_document = None

        if transcript_path:
            default_name = os.path.splitext(os.path.basename(transcript_path))[0] + ".txt"
        else:
            default_name = "transcript.txt"
        memo_lines = ["Transcribed with noScribe, sent from noScribeEdit."]
        if transcript_path:
            memo_lines.append(f"Transcript file: {transcript_path}")
        if audio_source:
            memo_lines.append(f"Audio file: {audio_source}")

        form = QtWidgets.QFormLayout()
        self.endpoint_edit = QtWidgets.QLineEdit(str(config.get(CONFIG_ENDPOINT_KEY, DEFAULT_ENDPOINT)))
        self.endpoint_edit.setToolTip("Address shown in QualCoder when the external MCP server starts")
        self.test_button = QtWidgets.QPushButton("Test connection")
        self.test_button.clicked.connect(self.test_connection)
        endpoint_row = QtWidgets.QHBoxLayout()
        endpoint_row.addWidget(self.endpoint_edit, 1)
        endpoint_row.addWidget(self.test_button)
        form.addRow("QualCoder MCP address:", endpoint_row)

        self.name_edit = QtWidgets.QLineEdit(default_name)
        form.addRow("Document name:", self.name_edit)

        self.timestamps_combo = QtWidgets.QComboBox()
        for key, label in TIMESTAMP_CHOICES:
            self.timestamps_combo.addItem(label, key)
        saved_choice = str(config.get(CONFIG_TIMESTAMPS_KEY, TIMESTAMP_CHOICES[0][0]))
        index = self.timestamps_combo.findData(saved_choice)
        self.timestamps_combo.setCurrentIndex(index if index >= 0 else 0)
        self.timestamps_combo.setToolTip(
            "[hh:mm:ss] stamps let QualCoder's A/V coding jump to the audio position")
        self.timestamps_combo.currentIndexChanged.connect(self._update_preview)
        form.addRow("Timestamps:", self.timestamps_combo)

        self.memo_edit = QtWidgets.QPlainTextEdit("\n".join(memo_lines))
        self.memo_edit.setFixedHeight(70)
        form.addRow("Memo:", self.memo_edit)

        self.preview = QtWidgets.QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(160)
        form.addRow("Preview:", self.preview)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)

        buttons = QtWidgets.QDialogButtonBox()
        self.send_button = buttons.addButton("Send", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.send)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addWidget(buttons)
        self._update_preview()

    def _current_text(self) -> str:
        return transcript_to_text(self._html_str, self._html_node_to_text, self.timestamps_combo.currentData())

    def _update_preview(self):
        text = self._current_text()
        self.preview.setPlainText(text[:3000] + ("\n[...]" if len(text) > 3000 else ""))
        self.status_label.setText(f"{len(text):,} characters")

    def _client(self) -> QualCoderMcpClient:
        endpoint = self.endpoint_edit.text().strip() or DEFAULT_ENDPOINT
        self._config[CONFIG_ENDPOINT_KEY] = endpoint
        return QualCoderMcpClient(endpoint)

    def _set_busy(self, busy: bool, message: str = ""):
        for widget in (self.send_button, self.test_button, self.endpoint_edit, self.name_edit,
                       self.timestamps_combo, self.memo_edit):
            widget.setEnabled(not busy)
        if message:
            self.status_label.setText(message)

    def _run(self, func, on_success):
        self._worker = _RequestWorker(func, self)
        self._worker.succeeded.connect(on_success)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(lambda: self._set_busy(False))
        self._set_busy(True, "Contacting QualCoder...")
        self._worker.start()

    def _on_failed(self, message: str):
        self.status_label.setText("")
        QtWidgets.QMessageBox.critical(self, "QualCoder", message)

    def test_connection(self):
        client = self._client()
        self._run(client.project_status, self._on_status)

    def _on_status(self, status):
        project = str(status.get("project_name", "")).strip() or "(unnamed project)"
        permission = str(status.get("ai_permission_level", ""))
        version = str(status.get("qualcoder_version", ""))
        message = f'Connected to QualCoder {version}, project "{project}".'
        if permission == "read_only":
            message += ('\nAI permissions are "Read only" in QualCoder; set them to "Sandboxed" or '
                        '"Full access" before sending.')
        self.status_label.setText(message)

    def send(self, rename_if_exists: bool = False):
        name = " ".join(self.name_edit.text().split()).strip()
        if name == "":
            QtWidgets.QMessageBox.warning(self, "QualCoder", "Please enter a document name.")
            return
        text = self._current_text()
        if text.strip() == "":
            QtWidgets.QMessageBox.warning(self, "QualCoder", "The transcript is empty.")
            return
        self._config[CONFIG_TIMESTAMPS_KEY] = self.timestamps_combo.currentData()
        memo = self.memo_edit.toPlainText()
        client = self._client()
        self._run(
            lambda: client.create_text_document(name, text, memo, rename_if_exists),
            self._on_sent,
        )

    def _on_sent(self, payload):
        document = payload.get("document", {}) if isinstance(payload, dict) else {}
        if not payload.get("created", False):
            if payload.get("reason") == "already_exists":
                answer = QtWidgets.QMessageBox.question(
                    self, "QualCoder",
                    f'The project already has a document named "{document.get("name", "")}".\n\n'
                    "Send the transcript as a new document with a numbered suffix?",
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.Yes,
                )
                if answer == QtWidgets.QMessageBox.StandardButton.Yes:
                    self.send(rename_if_exists=True)
                return
            QtWidgets.QMessageBox.warning(self, "QualCoder", f"QualCoder did not create the document.\n{payload}")
            return
        self.result_document = document
        QtWidgets.QMessageBox.information(
            self, "QualCoder",
            f'Transcript sent to QualCoder as "{document.get("name", "")}" (id {document.get("fid", "?")}).\n'
            "It is now listed in Manage files.",
        )
        self.accept()
