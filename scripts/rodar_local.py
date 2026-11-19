"""Roda o monitor no seu computador e publica o histórico no GitHub.

Para que serve: o Pelando bloqueia os servidores do GitHub Actions, mas aceita o seu computador.
Rodando aqui a cada 10 minutos (Agendador de Tarefas do Windows), o Pelando também é monitorado,
e o histórico compartilhado mantém a página e o anti-spam iguais aos do GitHub.

Funciona SOMENTE dentro de um clone dedicado do repositório (que tenha o arquivo .runner na raiz),
porque a cada execução ele descarta mudanças locais e sincroniza com o GitHub. Nunca aponte o
Agendador para a sua pasta de trabalho.

O tópico do ntfy é lido de %LOCALAPPDATA%\\ps5vem\\ntfy_topic.txt (fora do repositório).
O log fica em %LOCALAPPDATA%\\ps5vem\\monitor-local.log.

Instalação: veja a seção "Rodar também no seu computador" do README.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ps5vem"
ARQ_TOPICO = PASTA_DADOS / "ntfy_topic.txt"
ARQ_LOG = PASTA_DADOS / "monitor-local.log"
ARQ_TRAVA = PASTA_DADOS / "rodando.lock"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_LINHAS_LOG = 3000


def log(msg: str) -> None:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    with ARQ_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%d/%m %H:%M:%S} {msg}\n")


def podar_log() -> None:
    if ARQ_LOG.exists():
        linhas = ARQ_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(linhas) > MAX_LINHAS_LOG:
            ARQ_LOG.write_text("\n".join(linhas[-MAX_LINHAS_LOG:]) + "\n", encoding="utf-8")


def rodar(*cmd: str, env: dict | None = None, checar: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, creationflags=SEM_JANELA, timeout=480)
    if checar and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} falhou ({r.returncode}): {(r.stderr or r.stdout).strip()[-400:]}")
    return r


def python_console() -> str:
    """O Agendador chama pythonw.exe (sem janela); o monitor roda com python.exe, também sem janela."""
    exe = Path(sys.executable)
    alt = exe.with_name("python.exe")
    return str(alt if exe.name.lower() == "pythonw.exe" and alt.exists() else exe)


def main() -> int:
    if not (RAIZ / ".runner").exists():
        log(f"ERRO: {RAIZ} não é o clone dedicado (falta o arquivo .runner). Nada foi feito.")
        return 2
    if not ARQ_TOPICO.exists() or not ARQ_TOPICO.read_text(encoding="utf-8").strip():
        log(f"ERRO: tópico do ntfy não encontrado em {ARQ_TOPICO}.")
        return 2

    # evita duas execuções ao mesmo tempo (ex.: o PC acordou e o Agendador disparou atrasado)
    if ARQ_TRAVA.exists() and time.time() - ARQ_TRAVA.stat().st_mtime < 9 * 60:
        log("Outra execução ainda está rodando; pulando esta.")
        return 0
    ARQ_TRAVA.write_text(str(os.getpid()), encoding="utf-8")
    try:
        # 1) sincroniza com o GitHub (código novo + histórico mais recente)
        rodar("git", "fetch", "--quiet", "origin")
        rodar("git", "reset", "--quiet", "--hard", "origin/main")

        # 2) roda o monitor
        env = {**os.environ, "NTFY_TOPIC": ARQ_TOPICO.read_text(encoding="utf-8").strip(), "PYTHONIOENCODING": "utf-8"}
        r = rodar(python_console(), "monitor.py", env=env, checar=False)
        resumo = [l for l in r.stdout.splitlines()
                  if any(k in l for k in ("anúncios encontrados", "BLOQUEADA", "ERRO", "ENVIAR", "Notificação", "Fora do período"))]
        for l in resumo:
            log("  " + l[9:].strip())
        if r.returncode != 0:
            log(f"monitor terminou com código {r.returncode}: {r.stderr.strip()[-300:]}")

        # 3) publica o histórico, se mudou
        if rodar("git", "status", "--porcelain", "--", "data/history.json").stdout.strip():
            rodar("git", "add", "data/history.json")
            rodar("git", "commit", "--quiet", "-m", "chore: atualiza histórico (computador) [skip ci]")
            if rodar("git", "push", "--quiet", "origin", "HEAD:main", checar=False).returncode != 0:
                # o GitHub Actions publicou no meio do caminho: tenta encaixar por cima uma vez
                rebase = rodar("git", "pull", "--quiet", "--rebase", "origin", "main", checar=False)
                if rebase.returncode != 0:
                    rodar("git", "rebase", "--abort", checar=False)
                    log("Conflito com o histórico do GitHub; esta execução não foi publicada (a próxima corrige).")
                else:
                    rodar("git", "push", "--quiet", "origin", "HEAD:main")
                    log("Histórico publicado (após sincronizar).")
            else:
                log("Histórico publicado.")
        return 0
    except Exception as e:  # noqa: BLE001
        log(f"ERRO: {e}")
        return 1
    finally:
        ARQ_TRAVA.unlink(missing_ok=True)
        podar_log()


if __name__ == "__main__":
    sys.exit(main())
