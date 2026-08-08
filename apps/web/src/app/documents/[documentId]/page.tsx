import Link from "next/link";
import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { ExternalIcon, FileIcon } from "@/components/icons";
import { documentPdfUrl, fetchDocumentDetail } from "@/lib/api";
import { fallbackCitation, fallbackDocuments } from "@/lib/sample-data";

type DocumentDetailPageProps = {
  params: Promise<{ documentId: string }>;
};

type DocumentDetail = {
  document_id: string;
  title: string;
  short_title: string;
  regulation_type: string;
  number: number;
  year: number;
  issuer: string;
  topics: string[];
  legal_status: string;
  source_url: string;
  source_name: string;
  file_name: string;
  verification_status: string;
  chunk_count: number;
  available_chunks: { chunk_id: string; article: string; paragraph: string; page_start: number; page_end: number }[];
};

function formatStatus(status: string) {
  if (status === "active") return "Berlaku";
  if (status === "needs_verification") return "Perlu verifikasi";
  return status.replaceAll("_", " ");
}

export default async function DocumentDetailPage({ params }: DocumentDetailPageProps) {
  const { documentId } = await params;

  let document: DocumentDetail | null = null;
  let fromFallback = false;
  try {
    const detail = await fetchDocumentDetail(documentId);
    if (detail && detail.document_id) {
      document = detail as unknown as DocumentDetail;
    }
  } catch {
    const fallback = fallbackDocuments.find((item) => item.document_id === documentId);
    if (fallback) {
      document = {
        ...fallback,
        issuer: "Pemerintah Republik Indonesia",
        source_url: fallback.source_url ?? "",
        source_name: "Katalog referensi lokal",
        file_name: `${fallback.document_id}.pdf`,
        verification_status: "pending_detail_url",
        chunk_count: 0,
        available_chunks: [
          {
            chunk_id: fallbackCitation.chunk_id,
            article: fallbackCitation.article,
            paragraph: fallbackCitation.paragraph,
            page_start: fallbackCitation.page_start,
            page_end: fallbackCitation.page_end,
          },
        ],
      } as unknown as DocumentDetail;
      fromFallback = true;
    }
  }
  if (!document) {
    notFound();
  }

  return (
    <AppShell>
      <section className="document-detail">
        <Link href="/search" className="back-link">
          Kembali ke pencarian
        </Link>
        <div className="page-heading">
          <h1>{document.title}</h1>
          <p>
            {document.regulation_type} Nomor {document.number} Tahun {document.year}
          </p>
        </div>
        {fromFallback ? (
          <p className="search-fallback-note" role="status">
            API detail belum tersedia. Menampilkan data katalog referensi lokal sementara.
          </p>
        ) : null}
        <div className="detail-grid">
          <article className="detail-panel">
            <h2>Metadata</h2>
            <dl className="source-meta">
              <div>
                <dt>Status hukum</dt>
                <dd>{formatStatus(document.legal_status)}</dd>
              </div>
              <div>
                <dt>Topik</dt>
                <dd>{document.topics.map((item) => item.replaceAll("_", " ")).join(", ")}</dd>
              </div>
              <div>
                <dt>Sumber</dt>
                <dd>
                  <a href={document.source_url || documentPdfUrl(document.document_id)} target="_blank" rel="noreferrer">
                    {document.source_name || "Buka sumber resmi"}
                    <ExternalIcon className="icon inline-icon" />
                  </a>
                </dd>
              </div>
              <div>
                <dt>Berkas asli</dt>
                <dd>
                  <a href={documentPdfUrl(document.document_id)} target="_blank" rel="noreferrer">
                    {document.file_name || "Buka PDF dataset"}
                    <ExternalIcon className="icon inline-icon" />
                  </a>
                </dd>
              </div>
              {document.chunk_count > 0 ? (
                <div>
                  <dt>Chunk terindeks</dt>
                  <dd>{document.chunk_count} segmen siap di-retrieval</dd>
                </div>
              ) : null}
            </dl>
          </article>
          <article className="detail-panel source-viewer">
            <h2>Source viewer</h2>
            {document.available_chunks?.length ? (
              <ul className="viewer-chunk-list">
                {document.available_chunks.map((chunk) => (
                  <li key={chunk.chunk_id} className="viewer-page">
                    <FileIcon className="icon" />
                    <strong>{chunk.article}</strong>
                    <small>
                      {chunk.paragraph ? `${chunk.paragraph} · ` : ""}
                      Halaman {chunk.page_start}
                      {chunk.page_end !== chunk.page_start ? `-${chunk.page_end}` : ""}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="viewer-page">
                <FileIcon className="icon" />
                <p>Dokumen belum terindeks — jalankan ingestion dari panel admin.</p>
              </div>
            )}
          </article>
        </div>
      </section>
    </AppShell>
  );
}
