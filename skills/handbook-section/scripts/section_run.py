#!/usr/bin/env python3
"""Local call ledger; never launches models or certifies content acceptance."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys

import yaml


KINDS = ("plan", "draft", "source", "translate", "bilingual")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def local(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Paths must remain inside the repository")
    return path


def hashes(root, paths):
    return {str(local(root, p).relative_to(root)): hashlib.sha256(
        local(root, p).read_bytes()).hexdigest() for p in paths}


def save(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def run(args):
    root = Path(args.root).resolve()
    schema = yaml.safe_load((root / "schema.yaml").read_text())
    if args.section not in schema["folders"]:
        raise ValueError("Unknown schema folder")
    # Resolve schema-controlled names as well as command-line paths.
    folder = local(root, "content/" + args.section)
    directory = local(root, ".section-runs/" + args.section)
    state_path = directory / "manifest.json"
    if args.command == "init":
        if state_path.exists():
            raise ValueError("Run already exists; use status to resume")
        entries = schema["folders"][args.section].get("articles", [])
        known = [entry["file"] for entry in entries
                 if entry.get("status") != "retired"]
        selected = args.article or known
        if len(set(selected)) != len(selected):
            raise ValueError("Need unique schema article filenames")
        if any(name not in known for name in selected):
            raise ValueError("Article is absent from the active schema list")
        articles = [str(local(root, str(folder / name)).relative_to(root))
                    for name in selected]
        estimate = len(articles) or schema["folders"][args.section].get("legacy_articles", 0)
        budget = args.call_budget if args.call_budget is not None else 2 * estimate + 5
        if budget < 1:
            raise ValueError("Call budget must be positive")
        directory.mkdir(parents=True, exist_ok=True)
        # Keep payloads, prompts and usage local without ignoring the skill itself.
        ignore = directory.parent / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*\n!.gitignore\n")
        data = {"version": 1, "section": args.section, "created": now(),
                "articles": articles, "call_budget": budget,
                "profile": args.profile, "review_pass_limit": 2 if args.profile == "agile" else 3,
                "calls": [], "events": [], "next_step": "Inspect prior work; reuse or prepare section plan"}
        save(state_path, data)
    else:
        data = json.loads(state_path.read_text())

    if args.command == "enroll":
        if any(call["outcome"] == "pending" for call in data["calls"]):
            raise ValueError("Finish pending call before changing scope")
        known = {entry["file"] for entry in schema["folders"][args.section].get("articles", [])
                 if entry.get("status") != "retired"}
        if any(name not in known for name in args.article):
            raise ValueError("Enroll only active schema filenames after planning/scaffolding")
        for name in args.article:
            article = str(local(root, str(folder / name)).relative_to(root))
            if article not in data["articles"]:
                data["articles"].append(article)
        save(state_path, data)
    elif args.command == 'attach':
        if args.call < 1 or args.call > len(data['calls']):
            raise ValueError('Unknown call')
        call = data['calls'][args.call - 1]
        if call['outcome'] == 'pending':
            raise ValueError('Finish the provider attempt before attaching recovery')
        call.setdefault('recoveries', []).append({'time': now(),
            'artifacts': hashes(root, args.artifact), 'note': args.note})
        save(state_path, data)
    elif args.command == "event":
        data.setdefault('events', []).append({'kind': args.kind, 'time': now(),
            'note': args.note, 'artifacts': hashes(root, args.artifact)})
        save(state_path, data)
    elif args.command == "start":
        if any(call["outcome"] == "pending" for call in data["calls"]):
            raise ValueError("Pending call: inspect its process/output before finishing or retrying")
        if len(data["calls"]) >= data["call_budget"]:
            raise ValueError("Call budget exhausted; do not reset or silently extend it")
        articles = args.article or ([] if args.kind == "plan" else data["articles"])
        if args.kind != "plan" and not articles:
            raise ValueError("Plan/scaffold schema articles and enroll them before content calls")
        if len(set(articles)) != len(articles) or any(a not in data["articles"] for a in articles):
            raise ValueError("Use unique article paths from this run's manifest")
        if args.kind in ("draft", "translate") and len(articles) != 1:
            raise ValueError("Generation calls must name exactly one article")
        if args.kind in ("source", "bilingual"):
            for article in articles:
                count = sum(c["kind"] == args.kind and article in c["articles"]
                            for c in data["calls"])
                if count >= data.get("review_pass_limit", 3):
                    raise ValueError("Per-article review cap reached; explicit disposition required")
        inputs = ["AUTHORING_GUIDE.md", *args.input]
        if args.kind in ("source", "translate", "bilingual"):
            for article in articles:
                if not local(root, article).is_file():
                    raise ValueError("Review/translation requires existing English inputs")
        inputs.extend(a for a in articles if local(root, a).exists())
        if args.kind == "bilingual":
            inputs.extend(a.removesuffix(".md") + ".sv.md" for a in articles)
        call = {"id": len(data["calls"]) + 1, "kind": args.kind,
                "articles": articles, "provider": args.provider, "model": args.model,
                "approval": args.approval, "started": now(), "outcome": "pending",
                "inputs": hashes(root, inputs)}
        data["calls"].append(call)
        data["next_step"] = "Inspect/finish call " + str(call["id"]) + "; do not launch it twice"
        save(state_path, data)
    elif args.command == "finish":
        if not data["calls"] or data["calls"][-1]["outcome"] != "pending":
            raise ValueError("No pending call to finish")
        call = data["calls"][-1]
        call.update({"outcome": args.outcome, "finished": now(),
                     "artifacts": hashes(root, args.artifact), "note": args.note})
        data["next_step"] = args.next_step
        save(state_path, data)

    # Currentness is reported, never stamped as source/bilingual acceptance.
    changed = []
    for call in data["calls"]:
        for name, digest in call["inputs"].items():
            path = local(root, name)
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                changed.append({"call": call["id"], "input": name})
    print(json.dumps({"manifest": str(state_path.relative_to(root)),
                      "section": data["section"], "articles": data["articles"],
                      "attempts": len(data["calls"]), "budget": data["call_budget"],
                      "pending": [c["id"] for c in data["calls"] if c["outcome"] == "pending"],
                      "changed_inputs": changed, "next_step": data["next_step"]}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Handbook root (default: current directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "status", "enroll", "start", "finish", "event", "attach"):
        command = commands.add_parser(name)
        command.add_argument("section", help="Folder key from schema.yaml")
        if name == "init":
            command.add_argument("--article", action="append", help="Schema filename; repeat for subset")
            command.add_argument("--call-budget", type=int)
            command.add_argument("--profile", choices=("agile", "pilot"), default="agile")
        elif name == "enroll":
            command.add_argument("--article", action="append", required=True, help="New schema filename")
        elif name == "start":
            command.add_argument("--kind", choices=KINDS, required=True)
            command.add_argument("--article", action="append", help="Manifest article path; repeat for batch")
            command.add_argument("--provider", required=True)
            command.add_argument("--model", required=True)
            command.add_argument("--approval", required=True, help="Existing authorization reference")
            command.add_argument("--input", action="append", required=True,
                                 help="Actual prompt/payload/source file, relative to root; repeat")
        elif name == 'attach':
            command.add_argument('--call', type=int, required=True)
            command.add_argument('--artifact', action='append', required=True)
            command.add_argument('--note', required=True)
        elif name == 'event':
            command.add_argument('--kind', choices=('human_interruption', 'mechanical_repair'), required=True)
            command.add_argument('--note', required=True)
            command.add_argument('--artifact', action='append', required=True)
        elif name == "finish":
            command.add_argument("--outcome", choices=("completed", "failed", "unknown"), required=True)
            command.add_argument("--artifact", action="append", required=True,
                                 help="Result/error/incident record relative to root; repeat")
            command.add_argument("--note", required=True, help="Actual result, usage and evidence disposition")
            command.add_argument("--next-step", required=True)
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError, KeyError, yaml.YAMLError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
