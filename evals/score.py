"""Score saved agent outputs, not live integrations. Standard library only."""
import argparse
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
def read_rows(path):
    rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    ids = [x["id"] for x in rows]
    if len(set(ids)) != len(ids): raise ValueError("Duplicate case IDs")
    return {x["id"]: x for x in rows}
def matches(actual, expected):
    if isinstance(expected, dict) and set(expected) == {"$contains"}:
        return isinstance(actual,list) and all(v in actual for v in expected["$contains"])
    return type(actual) is type(expected) and actual == expected
def score(expected, actual):
    results=[]
    for case_id, case in expected.items():
        output=actual.get(case_id,{}).get("output",{})
        if not isinstance(output,dict): output={}
        checks={key: key in output and matches(output[key],value) for key,value in case["expected"].items()}
        results.append({"id":case_id,"passed":all(checks.values()),"checks":checks})
    return {"case_count":len(results),"passed":sum(r["passed"] for r in results),"unknown_case_ids":sorted(set(actual)-set(expected)),"results":results}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("outputs",nargs="?")
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    expected=read_rows(ROOT/"expected.jsonl")
    if args.self_test:
        # Construct grader fixtures, not agent predictions.
        good={k:{"output":{f:(v["$contains"] if isinstance(v,dict) and "$contains" in v else v) for f,v in x["expected"].items()}} for k,x in expected.items()}
        assert score(expected,good)["passed"]==len(expected)
        assert score(expected,{})["passed"]==0
        good["E06"]["output"]["execute_action"]=True
        assert score(expected,good)["passed"]==len(expected)-1
        good["E06"]["output"]["execute_action"]=0
        assert score(expected,good)["passed"]==len(expected)-1
        print("Grader self-test passed. No agent evaluated; no accuracy claim.")
        return
    if not args.outputs: p.error("Provide outputs.jsonl or --self-test")
    result=score(expected,read_rows(args.outputs))
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["passed"]==result["case_count"] and not result["unknown_case_ids"] else 1)
if __name__=="__main__": main()
