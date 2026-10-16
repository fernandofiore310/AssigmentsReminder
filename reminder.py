"""Daily Canvas digest. Python 3.11+, no third-party dependencies."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    parser = PlainText()
    parser.feed(value or "")
    return " ".join(" ".join(parser.parts).split())


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class Canvas:
    def __init__(self, base, token):
        self.base = base.rstrip("/")
        if urlsplit(self.base).scheme != "https":
            raise ValueError("CANVAS_BASE_URL precisa usar HTTPS.")
        self.token = token

    def pages(self, path, params=None):
        url = self.base + "/api/v1/" + path
        url += "?" + urlencode({"per_page": 100, **(params or {})}, doseq=True)
        seen = set()
        while url:
            # Never forward a Canvas credential to a different origin.
            if urlsplit(url)[:2] != urlsplit(self.base)[:2] or url in seen:
                raise ValueError("Link de paginação inválido recebido do Canvas.")
            seen.add(url)
            req = Request(url, headers={"Authorization": "Bearer " + self.token})
            # Disable redirects so credentials cannot follow a redirect off-site.
            from urllib.request import HTTPRedirectHandler, build_opener

            class NoRedirect(HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None

            with build_opener(NoRedirect()).open(req, timeout=30) as response:
                rows = json.load(response)
                if not isinstance(rows, list):
                    raise ValueError("Resposta inesperada da API do Canvas.")
                yield from rows
                link = response.headers.get("Link", "")
                match = re.search(r'<([^>]+)>;\s*rel="next"', link)
                url = urljoin(url, match.group(1)) if match else None


def collect(canvas, now, days):
    assignments, announcements = [], []
    courses = canvas.pages("courses", {"enrollment_state": "active", "enrollment_type": "student"})
    for course in courses:
        if course.get("access_restricted_by_date"):
            continue
        cid = course["id"]
        name = course.get("name", str(cid))
        for item in canvas.pages(f"courses/{cid}/assignments", {"include[]": "submission"}):
            submission = item.get("submission") or {}
            if item.get("published") is False or item.get("locked_for_user"):
                continue
            if submission.get("excused"):
                continue
            if not submission.get("missing") and submission.get("workflow_state") in {"submitted", "pending_review", "graded"}:
                continue
            if item.get("submission_types") == ["not_graded"]:
                continue
            due = timestamp(item.get("due_at"))
            if due is None or due <= now + timedelta(days=days):
                assignments.append({"course": name, "title": item["name"], "due": due,
                                    "url": item.get("html_url", "")})
        for item in canvas.pages("announcements", {"context_codes[]": f"course_{cid}",
                                 "start_date": (now - timedelta(days=7)).isoformat(),
                                 "end_date": now.isoformat()}):
            announcements.append({"course": name, "title": item["title"],
                                  "text": plain(item.get("message"))[:500],
                                  "date": timestamp(item.get("posted_at")),
                                  "url": item.get("html_url", "")})
    assignments.sort(key=lambda a: a["due"] or datetime.max.replace(tzinfo=timezone.utc))
    announcements.sort(key=lambda a: a["date"] or now, reverse=True)
    return assignments, announcements


def render(assignments, announcements, now, tz, days):
    lines = [f"bCourses • {now.astimezone(tz):%d/%m/%Y}",
             f"\nTarefas: atrasadas, próximos {days} dias e sem prazo"]
    if not assignments:
        lines.append("Nenhuma tarefa pendente nesse período.")
    for item in assignments:
        due = item["due"]
        label = due.astimezone(tz).strftime("%d/%m às %H:%M") if due else "sem prazo"
        if due and due < now:
            label = "ATRASADA — " + label
        lines.extend([f"• {item['course']} — {item['title']}", f"  {label}", item["url"]])
    lines.append("\nAnúncios dos últimos 7 dias")
    if not announcements:
        lines.append("Nenhum anúncio nesse período.")
    for item in announcements:
        lines.extend([f"• {item['course']} — {item['title']}", item["text"], item["url"]])
    lines.append("\nHorários: " + str(tz))
    return "\n".join(lines)


def required(name):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Configure {name} no ambiente (não envie o valor no chat).")
    return value


def send(text, channel):
    if channel == "console":
        print(text)
    elif channel == "telegram":
        token, chat = required("TELEGRAM_BOT_TOKEN"), required("TELEGRAM_CHAT_ID")
        # Stay below Telegram's UTF-16 length limit, including emoji.
        for start in range(0, len(text), 1800):
            payload = json.dumps({"chat_id": chat, "text": text[start:start + 1800]}).encode()
            request = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload,
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=30) as response:
                if not json.load(response).get("ok"):
                    raise ValueError("Telegram não confirmou o envio.")
    else:
        message = EmailMessage()
        message["Subject"] = "Seu resumo diário do bCourses"
        message["From"] = required("SMTP_FROM")
        message["To"] = required("REMINDER_EMAIL")
        message.set_content(text)
        with smtplib.SMTP(required("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587")), timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(required("SMTP_USER"), required("SMTP_PASSWORD"))
            smtp.send_message(message)


def run(args):
    now = datetime.now(timezone.utc)
    canvas = Canvas(os.getenv("CANVAS_BASE_URL", "https://bcourses.berkeley.edu"), required("CANVAS_TOKEN"))
    assignments, announcements = collect(canvas, now, args.days)
    send(render(assignments, announcements, now, ZoneInfo(args.timezone), args.days), args.channel)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=["console", "telegram", "email"], default="console")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--timezone", default="America/Los_Angeles")
    parser.add_argument("--daily-at", help="Ficar em execução e enviar diariamente, HH:MM no fuso escolhido")
    parser.add_argument("--state", default=".reminder-state.json")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days precisa ser positivo")
    tz = ZoneInfo(args.timezone)
    if not args.daily_at:
        run(args)
        return
    try:
        hour, minute = map(int, args.daily_at.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        parser.error("--daily-at precisa estar no formato HH:MM válido")
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    key = f"{args.channel}:{args.timezone}:{args.daily_at}"
    print(f"Aguardando envio diário às {args.daily_at} ({tz}).", flush=True)
    while True:
        now = datetime.now(tz)
        today = now.date().isoformat()
        if (now.hour, now.minute) >= (hour, minute) and state.get(key) != today:
            try:
                run(args)
                state[key] = today
                temporary = state_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(state))
                temporary.replace(state_path)
                print(f"Resumo enviado: {today}", flush=True)
            except (HTTPError, URLError, ValueError, OSError):
                # Do not log exception URLs: Telegram URLs contain the bot token.
                print("Envio falhou; verifique conexão, credenciais e permissões. Nova tentativa em 5 minutos.", file=sys.stderr, flush=True)
                time.sleep(300)
                continue
        time.sleep(30)


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        print(f"Serviço retornou HTTP {error.code}. Verifique credenciais e permissões.", file=sys.stderr)
        sys.exit(1)
    except (URLError, ValueError, OSError):
        print("Não foi possível concluir. Verifique as variáveis obrigatórias, a conexão e as permissões.", file=sys.stderr)
        sys.exit(1)
