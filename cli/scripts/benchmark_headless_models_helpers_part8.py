from __future__ import annotations

SOURCE_PART = r'''        "cases": [{"provider": case.provider, "model": case.model} for case in cases],
        "results": results,
        "summary": summary,
        "overall_summary": overall_summary,
        "ability_matrix": _build_ability_matrix(summary) if ability_tests else {},
    }

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if ability_tests:
            _print_ability_table(results, summary, overall_summary)
        else:
            _print_table(results, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
