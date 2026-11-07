"use client";

// 한 페이지: 역할 선택, 질문, SQL 보기, 결과 표 (docs/plan.md M4 "화면").
// 화면은 /generate와 /execute만 부른다. 권한은 화면이 아니라 execute()가 강제하므로,
// SQL 칸을 고쳐 실행해도 같은 범위만 나온다.

import { FormEvent, useEffect, useState } from "react";

type Persona = { login: string; role: string };
type Cell = string | number | boolean | null;
type Rows = { columns: string[]; rows: Cell[][]; truncated: boolean; warnings: string[] };
type ApiError = { kind: string; message: string };

const KIND_LABEL: Record<string, string> = {
  generation_error: "SQL 생성 실패",
  guard_rejected: "권한 검사에서 거부",
  execution_error: "실행 실패",
};

async function call<T>(path: string, body?: object): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    throw typeof detail === "object" && detail?.kind
      ? (detail as ApiError)
      : { kind: "error", message: `API 오류 (${res.status})` };
  }
  return data as T;
}

export default function Home() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [user, setUser] = useState("sales.kim");
  const [question, setQuestion] = useState("");
  const [sql, setSql] = useState("");
  const [model, setModel] = useState("");
  const [result, setResult] = useState<Rows | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<"" | "generate" | "execute">("");

  useEffect(() => {
    call<Persona[]>("/users")
      .then(setPersonas)
      .catch((e: ApiError) => setError(e));
  }, []);

  async function run(sqlToRun: string) {
    setBusy("execute");
    setError(null);
    setResult(null);
    try {
      setResult(await call<Rows>("/execute", { sql: sqlToRun, user }));
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy("");
    }
  }

  async function ask(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy("generate");
    setError(null);
    setResult(null);
    setSql("");
    try {
      const generated = await call<{ sql: string; model: string }>("/generate", { question, user });
      setSql(generated.sql);
      setModel(generated.model);
      await run(generated.sql);
    } catch (e) {
      setError(e as ApiError);
      setBusy("");
    }
  }

  return (
    <main>
      <h1>ERP 자연어 질의</h1>
      <p className="sub">Odoo 데이터를 한국어로 물어보세요. 결과는 고른 사용자가 Odoo에서 볼 수 있는 범위로만 나옵니다.</p>

      <form onSubmit={ask}>
        <div className="row">
          <label htmlFor="user">사용자</label>
          <select id="user" value={user} onChange={(e) => setUser(e.target.value)}>
            {personas.map((p) => (
              <option key={p.login} value={p.login}>
                {p.login} ({p.role})
              </option>
            ))}
          </select>
        </div>
        <label htmlFor="question">질문</label>
        <textarea
          id="question"
          rows={2}
          value={question}
          placeholder="예: 지난달 확정된 판매 주문은 몇 건이야?"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask(e);
          }}
        />
        <div className="row">
          <button type="submit" disabled={busy !== "" || !question.trim()}>
            {busy === "generate" ? "SQL 만드는 중…" : "질문하기"}
          </button>
        </div>
      </form>

      {sql && (
        <section>
          <h2>SQL</h2>
          <p className="meta">{model}가 만든 SQL입니다. 고쳐서 다시 실행할 수 있고, 실행 전에 권한 검사를 거칩니다.</p>
          <textarea className="sql" rows={Math.min(16, Math.max(6, sql.split("\n").length + 1))} value={sql} onChange={(e) => setSql(e.target.value)} />
          <div className="row">
            <button type="button" className="secondary" disabled={busy !== ""} onClick={() => run(sql)}>
              {busy === "execute" ? "실행 중…" : "이 SQL 실행"}
            </button>
          </div>
        </section>
      )}

      {error && (
        <section className="error" role="alert">
          <strong>{KIND_LABEL[error.kind] ?? "오류"}</strong>: {error.message}
        </section>
      )}

      {result && <ResultTable rows={result} />}
    </main>
  );
}

function ResultTable({ rows }: { rows: Rows }) {
  return (
    <section>
      <h2>결과</h2>
      <p className="meta">
        {rows.rows.length}행{rows.truncated ? " (행 수 제한으로 잘림)" : ""}
      </p>
      {rows.warnings.map((w) => (
        <p key={w} className="warn">
          주의: {w}
        </p>
      ))}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {rows.columns.map((c, i) => (
                <th key={i}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.rows.map((r, i) => (
              <tr key={i}>
                {r.map((v, j) => (
                  <td key={j} className={v === null ? "null" : typeof v === "number" ? "num" : undefined}>
                    {v === null ? "NULL" : typeof v === "number" ? v.toLocaleString("ko-KR") : String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
