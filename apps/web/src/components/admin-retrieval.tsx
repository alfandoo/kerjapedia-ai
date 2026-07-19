"use client";

import { useState } from "react";

import { AlertIcon, CheckIcon, PlayIcon } from "./icons";
import { runRetrievalPlayground } from "@/lib/api";
import { fallbackRetrievalResults } from "@/lib/sample-data";
import type { RetrievalPlaygroundResult } from "@/lib/types";

export function AdminRetrieval() {
  const [question, setQuestion] = useState("Apakah pekerja PKWT berhak mendapat uang kompensasi?");
  const [topK, setTopK] = useState(5);
  const [results, setResults] = useState(fallbackRetrievalResults);
  const [selectedId, setSelectedId] = useState(fallbackRetrievalResults[0].chunk_id);
  const [latency, setLatency] = useState(184);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("Hasil contoh siap untuk ditinjau.");
  const selected = results.find((item) => item.chunk_id === selectedId) ?? null;

  async function run() {
    setRunning(true);
    setStatus("Menjalankan hybrid retrieval dan rerank...");
    try {
      const response = await runRetrievalPlayground(question, topK);
      setResults(response.results);
      setSelectedId(response.results[0]?.chunk_id ?? "");
      setLatency(response.latency_ms);
      setWarnings(response.warnings);
      setStatus(
        response.should_refuse ? "Hasil berada di bawah ambang jawaban." : "Retrieval selesai."
      );
    } catch {
      setStatus("API belum tersedia; hasil contoh tetap ditampilkan.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="admin-standard-page retrieval-page">
      <div className="admin-page-heading">
        <div>
          <h1>Retrieval Playground</h1>
          <p>Uji retrieval sebelum perubahan dipublikasikan.</p>
        </div>
      </div>
      <div className="retrieval-workspace">
        <aside className="retrieval-config">
          <label>
            Pertanyaan uji
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
          </label>
          <label>
            Top K
            <input
              type="number"
              min={1}
              max={10}
              value={topK}
              onChange={(event) => setTopK(Number(event.target.value))}
            />
          </label>
          <label>
            Mode retrieval
            <select defaultValue="hybrid">
              <option value="hybrid">Hybrid + rerank</option>
              <option value="dense">Dense</option>
              <option value="lexical">Lexical</option>
            </select>
          </label>
          <label>
            Topik
            <select defaultValue="pkwt">
              <option value="pkwt">PKWT</option>
              <option value="phk">PHK</option>
              <option value="pengupahan">Pengupahan</option>
            </select>
          </label>
          <label>
            Status hukum
            <select defaultValue="active">
              <option value="active">Berlaku</option>
              <option value="all">Semua status</option>
            </select>
          </label>
          <button
            type="button"
            className="admin-primary-button"
            disabled={running || question.trim().length < 4}
            onClick={() => void run()}
          >
            <PlayIcon className="icon" />
            {running ? "Menjalankan..." : "Jalankan retrieval"}
          </button>
          <p className="admin-inline-message" role="status">
            {status}
          </p>
        </aside>

        <div className="retrieval-results-panel">
          <div className="retrieval-results-heading">
            <h2>Hasil retrieval</h2>
            <span>{latency} ms</span>
          </div>
          <div className="retrieval-table">
            <div className="retrieval-row table-header">
              <span>#</span>
              <span>Dokumen & judul singkat</span>
              <span>Pasal / Halaman</span>
              <span>Skor</span>
              <span>Aksi</span>
            </div>
            {results.map((result, index) => (
              <div
                className={
                  result.chunk_id === selectedId ? "retrieval-row selected" : "retrieval-row"
                }
                key={result.chunk_id}
              >
                <span>{index + 1}</span>
                <span>
                  <strong>{result.short_title}</strong>
                  <small>{result.chunk_id}</small>
                </span>
                <span>
                  {result.article ?? "-"}
                  <small>Hal. {result.page_start}</small>
                </span>
                <span>
                  <strong>{result.final_score.toFixed(2)}</strong>
                  <i className="score-track">
                    <i style={{ width: `${Math.min(100, result.final_score * 100)}%` }} />
                  </i>
                </span>
                <span>
                  <button
                    type="button"
                    className="admin-text-link"
                    onClick={() => setSelectedId(result.chunk_id)}
                  >
                    Lihat kutipan
                  </button>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <section className="retrieval-quote-panel">
        <h2>Kutipan terpilih</h2>
        {selected ? (
          <RetrievalQuote result={selected} warnings={warnings} />
        ) : (
          <p className="admin-empty-copy">Tidak ada chunk yang melewati filter.</p>
        )}
      </section>
    </section>
  );
}

function RetrievalQuote({
  result,
  warnings,
}: {
  result: RetrievalPlaygroundResult;
  warnings: string[];
}) {
  return (
    <>
      <blockquote>{result.quote}</blockquote>
      <dl className="retrieval-metrics">
        <div>
          <dt>Chunk ID</dt>
          <dd>{result.chunk_id}</dd>
        </div>
        <div>
          <dt>Halaman</dt>
          <dd>{result.page_start}</dd>
        </div>
        <div>
          <dt>Lexical</dt>
          <dd>{result.lexical_score.toFixed(2)}</dd>
        </div>
        <div>
          <dt>Vector</dt>
          <dd>{result.semantic_score.toFixed(2)}</dd>
        </div>
        <div>
          <dt>Rerank</dt>
          <dd>{result.rerank_score.toFixed(2)}</dd>
        </div>
      </dl>
      <div className={warnings.length ? "retrieval-warning warning" : "retrieval-warning success"}>
        {warnings.length ? <AlertIcon className="icon" /> : <CheckIcon className="icon" />}
        <span>{warnings.length ? warnings.join(", ") : "Tidak ada peringatan"}</span>
      </div>
    </>
  );
}
