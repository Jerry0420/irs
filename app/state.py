"""伺服器狀態管理：題目資料模型、票數統計、JSON 落盤。"""
import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

SAVE_DEBOUNCE_SECONDS = 0.5


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class Pin(BaseModel):
    id: str = Field(default_factory=_new_id)
    option_id: str
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class VoteRecord(BaseModel):
    """某位觀眾（voter_id）在本輪投下的票，供取消投票時反向撤銷。"""
    option_id: str
    pin_id: Optional[str] = None


class OptionIn(BaseModel):
    id: str = Field(default_factory=_new_id)
    label: str = ""
    image_url: Optional[str] = None

    @field_validator("label")
    @classmethod
    def strip_label(cls, v: str) -> str:
        return v.strip()


class QuestionIn(BaseModel):
    title: str
    type: Literal["text", "image4"]
    options: list[OptionIn]

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("題目文字不可為空")
        return v

    @model_validator(mode="after")
    def check_options(self) -> "QuestionIn":
        if self.type == "text":
            if len(self.options) < 2:
                raise ValueError("文字題至少需要 2 個選項")
            if any(not o.label for o in self.options):
                raise ValueError("文字題每個選項都需要文字")
        else:  # image4
            if len(self.options) != 4:
                raise ValueError("圖片題必須恰有 4 個圖片選項")
            if any(not o.image_url for o in self.options):
                raise ValueError("圖片題每個選項都需要圖片")
        return self


class Question(QuestionIn):
    id: str = Field(default_factory=_new_id)
    round: int = 0
    votes: dict[str, int] = Field(default_factory=dict)
    pins: list[Pin] = Field(default_factory=list)
    voters: dict[str, VoteRecord] = Field(default_factory=dict)

    def public(self) -> dict:
        return self.model_dump(exclude={"voters"})


def _seed_questions() -> list[Question]:
    def text_q(title: str, labels: list[str]) -> Question:
        return Question(title=title, type="text",
                        options=[OptionIn(label=l) for l in labels])

    def image_q(title: str, items: list[tuple[str, str]]) -> Question:
        return Question(title=title, type="image4",
                        options=[OptionIn(label=l, image_url=u) for l, u in items])

    return [
        text_q("今晚的安可曲，您想聽哪一首？", ["月亮代表我的心", "望春風"]),
        text_q("哪一種樂器的音色最觸動您？", ["小提琴", "大提琴", "長笛", "鋼琴", "豎琴"]),
        image_q("哪一幅情景最貼近您此刻的心情？", [
            ("山林晨霧", "/static/img/scene1.svg"),
            ("海洋波光", "/static/img/scene2.svg"),
            ("城市夜色", "/static/img/scene3.svg"),
            ("星空原野", "/static/img/scene4.svg"),
        ]),
        image_q("下半場您最期待的曲目氛圍？", [
            ("溫暖爐火", "/static/img/scene5.svg"),
            ("雨後花園", "/static/img/scene6.svg"),
            ("兒時庭院", "/static/img/scene7.svg"),
            ("遠方旅途", "/static/img/scene8.svg"),
        ]),
    ]


class AppState:
    #: 題目定義欄位（寫入 questions.json，適合入版控）
    DEFINITION_FIELDS = {"id", "title", "type", "options"}
    #: 投票結果欄位（寫入 results.json，執行期資料、不入版控）
    RESULT_FIELDS = {"round", "votes", "pins", "voters"}

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir or os.environ.get("IRS_DATA_DIR", "data"))
        self.file = self.data_dir / "questions.json"
        self.results_file = self.data_dir / "results.json"
        self.uploads_dir = self.data_dir / "uploads"
        self._last_written_defs: str | None = None
        self.questions: list[Question] = []
        self.active_question_id: Optional[str] = None
        self._save_task: Optional[asyncio.Task] = None
        self.load()

    # ---------- 持久化 ----------

    def load(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        if self.file.exists():
            raw = json.loads(self.file.read_text(encoding="utf-8"))
            # 舊格式相容：questions.json 內可能還帶著票數與 active_question_id
            self.questions = [Question(**q) for q in raw.get("questions", [])]
            self.active_question_id = raw.get("active_question_id")
            self._load_results()
            if self.active_question_id and not self.get(self.active_question_id):
                self.active_question_id = None
        else:
            self.questions = _seed_questions()
            self.active_question_id = self.questions[0].id if self.questions else None
            self._write()
        self.sweep_orphan_uploads()  # 啟動時順帶清理歷史孤兒檔

    def _load_results(self) -> None:
        if not self.results_file.exists():
            return
        raw = json.loads(self.results_file.read_text(encoding="utf-8"))
        self.active_question_id = raw.get("active_question_id", self.active_question_id)
        for q in self.questions:
            data = raw.get("results", {}).get(q.id)
            if not data:
                continue
            q.round = data.get("round", 0)
            q.votes = data.get("votes", {})
            q.pins = [Pin(**p) for p in data.get("pins", [])]
            q.voters = {k: VoteRecord(**v) for k, v in data.get("voters", {}).items()}

    @staticmethod
    def _atomic_write(path: Path, payload: dict) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _write(self) -> None:
        # 題目定義（入版控）：內容沒變就不重寫，投票期間 git 保持乾淨
        defs = {"questions": [q.model_dump(include=self.DEFINITION_FIELDS)
                              for q in self.questions]}
        defs_text = json.dumps(defs, ensure_ascii=False, sort_keys=True)
        if defs_text != self._last_written_defs:
            self._atomic_write(self.file, defs)
            self._last_written_defs = defs_text
        # 投票結果（不入版控）
        self._atomic_write(self.results_file, {
            "active_question_id": self.active_question_id,
            "results": {q.id: q.model_dump(include=self.RESULT_FIELDS)
                        for q in self.questions},
        })

    def save_soon(self) -> None:
        """Debounce 寫盤，避免大量投票時每票一次磁碟 IO。"""
        async def _later():
            await asyncio.sleep(SAVE_DEBOUNCE_SECONDS)
            self._write()

        try:
            if self._save_task and not self._save_task.done():
                return
            self._save_task = asyncio.get_running_loop().create_task(_later())
        except RuntimeError:  # 無事件迴圈（如同步測試情境）直接寫
            self._write()

    # ---------- 上傳檔案清理 ----------

    @staticmethod
    def _upload_urls(options) -> set[str]:
        return {o.image_url for o in options
                if o.image_url and o.image_url.startswith("/uploads/")}

    def _referenced_uploads(self) -> set[str]:
        refs: set[str] = set()
        for q in self.questions:
            refs |= self._upload_urls(q.options)
        return refs

    def sweep_orphan_uploads(self) -> list[str]:
        """掃描 uploads 目錄，刪除未被任何題目引用的檔案（含表單中換圖留下的舊圖）。"""
        referenced = {Path(u).name for u in self._referenced_uploads()}
        removed = []
        for f in self.uploads_dir.iterdir():
            if f.is_file() and not f.name.startswith(".") and f.name not in referenced:
                f.unlink()
                removed.append(f.name)
        return removed

    # ---------- 查詢 ----------

    def get(self, question_id: str) -> Optional[Question]:
        return next((q for q in self.questions if q.id == question_id), None)

    @property
    def active(self) -> Optional[Question]:
        return self.get(self.active_question_id) if self.active_question_id else None

    # ---------- CRUD ----------

    def create(self, data: QuestionIn) -> Question:
        q = Question(**data.model_dump())
        self.questions.append(q)
        self.sweep_orphan_uploads()  # 建題表單中換圖留下的舊上傳檔
        self.save_soon()
        return q

    def update(self, question_id: str, data: QuestionIn) -> Optional[Question]:
        q = self.get(question_id)
        if not q:
            return None
        q.title, q.type, q.options = data.title, data.type, data.options
        self.sweep_orphan_uploads()  # 換掉的圖若無人引用即刪檔
        valid_ids = {o.id for o in q.options}
        q.votes = {oid: n for oid, n in q.votes.items() if oid in valid_ids}
        q.pins = [p for p in q.pins if p.option_id in valid_ids]
        q.voters = {v: r for v, r in q.voters.items() if r.option_id in valid_ids}
        self.save_soon()
        return q

    def delete(self, question_id: str) -> bool:
        q = self.get(question_id)
        if not q:
            return False
        self.questions.remove(q)
        if self.active_question_id == question_id:
            self.active_question_id = None
        self.sweep_orphan_uploads()
        self.save_soon()
        return True

    def reorder(self, ids: list[str]) -> bool:
        """依 ids 順序重排題目；ids 必須恰為現有題目 id 的排列。"""
        if sorted(ids) != sorted(q.id for q in self.questions):
            return False
        by_id = {q.id: q for q in self.questions}
        self.questions = [by_id[i] for i in ids]
        self.save_soon()
        return True

    # ---------- 活動控制 ----------

    def activate(self, question_id: str) -> Optional[Question]:
        q = self.get(question_id)
        if not q:
            return None
        self.active_question_id = question_id
        self.save_soon()
        return q

    def reset(self, question_id: str) -> Optional[Question]:
        q = self.get(question_id)
        if not q:
            return None
        q.votes = {}
        q.pins = []
        q.voters = {}
        q.round += 1
        self.save_soon()
        return q

    def cast_vote(self, question_id: str, option_id: str, voter_id: str,
                  pin: Optional[Pin] = None) -> tuple[bool, str, Optional[Pin]]:
        q = self.get(question_id)
        if not q:
            return False, "question_not_found", None
        if question_id != self.active_question_id:
            return False, "not_active", None
        if voter_id in q.voters:
            return False, "already_voted", None
        if not any(o.id == option_id for o in q.options):
            return False, "option_not_found", None
        new_pin = None
        if q.type == "image4":
            if pin is None:
                return False, "pin_required", None
            new_pin = Pin(option_id=option_id, x=pin.x, y=pin.y)
            q.pins.append(new_pin)
        q.voters[voter_id] = VoteRecord(option_id=option_id,
                                        pin_id=new_pin.id if new_pin else None)
        q.votes[option_id] = q.votes.get(option_id, 0) + 1
        self.save_soon()
        return True, "ok", new_pin

    def cancel_vote(self, question_id: str, voter_id: str) -> tuple[bool, str, Optional[str]]:
        """撤銷 voter 在本輪的投票；回傳 (成功, 原因, 被移除的 pin id)。"""
        q = self.get(question_id)
        if not q:
            return False, "question_not_found", None
        if question_id != self.active_question_id:
            return False, "not_active", None
        record = q.voters.pop(voter_id, None)
        if record is None:
            return False, "not_voted", None
        if q.votes.get(record.option_id, 0) > 0:
            q.votes[record.option_id] -= 1
        if record.pin_id:
            q.pins = [p for p in q.pins if p.id != record.pin_id]
        self.save_soon()
        return True, "ok", record.pin_id
