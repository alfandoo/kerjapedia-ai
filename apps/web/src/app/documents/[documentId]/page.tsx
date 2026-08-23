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
      <section className="mx-auto w-full max-w-[1080px]">
        <Link
          href="/search"
          className="mb-5 inline-flex min-h-11 items-center gap-2.5 text-sm font-bold text-javanese transition hover:text-forest"
        >
          Kembali ke pencarian
        </Link>
        <div className="mb-6">
          <h1 className="font-display text-[clamp(36px,4vw,50px)] font-medium leading-[1.12] tracking-[-0.035em] text-javanese">
            {document.title}
          </h1>
          <p className="mt-1.5 text-sm leading-[1.75] text-muted-text">
            {document.regulation_type} Nomor {document.number} Tahun {document.year}
          </p>
        </div>
        {fromFallback ? (
          <p
            className="-mt-2 mb-6 flex items-center gap-2.5 border-l-[3px] border-[#bc8121] bg-[#fffaf0] px-3.5 py-2.5 text-[11px] text-[#6e531c]"
            role="status"
          >
            API detail belum tersedia. Menampilkan data katalog referensi lokal sementara.
          </p>
        ) : null}
        <div className="grid grid-cols-1 gap-4 min-[840px]:grid-cols-[320px_minmax(0,1fr)]">
          <article className="border-t border-[#dce4df] py-[22px]">
            <h2 className="mb-3 text-base font-bold text-tinta">Metadata</h2>
            <dl className="my-4 grid gap-2.5">
              <div className="grid grid-cols-1 gap-0.5 min-[840px]:grid-cols-[88px_minmax(0,1fr)]">
                <dt className="text-xs font-bold text-muted-text">Status hukum</dt>
                <dd className="text-[13px] text-tinta">{formatStatus(document.legal_status)}</dd>
              </div>
              <div className="grid grid-cols-1 gap-0.5 min-[840px]:grid-cols-[88px_minmax(0,1fr)]">
                <dt className="text-xs font-bold text-muted-text">Topik</dt>
                <dd className="text-[13px] text-tinta">
                  {document.topics.map((item) => item.replaceAll("_", " ")).join(", ")}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-0.5 min-[840px]:grid-cols-[88px_minmax(0,1fr)]">
                <dt className="text-xs font-bold text-muted-text">Sumber</dt>
                <dd className="text-[13px] text-tinta">
                  <a
                    href={document.source_url || documentPdfUrl(document.document_id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {document.source_name || "Buka sumber resmi"}
                    <ExternalIcon className="size-[18px] [stroke-width:1.8] ml-1 inline-block align-[-3px]" />
                  </a>
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-0.5 min-[840px]:grid-cols-[88px_minmax(0,1fr)]">
                <dt className="text-xs font-bold text-muted-text">Berkas asli</dt>
                <dd className="text-[13px] text-tinta">
                  <a href={documentPdfUrl(document.document_id)} target="_blank" rel="noreferrer">
                    {document.file_name || "Buka PDF dataset"}
                    <ExternalIcon className="size-[18px] [stroke-width:1.8] ml-1 inline-block align-[-3px]" />
                  </a>
                </dd>
              </div>
              {document.chunk_count > 0 ? (
                <div className="grid grid-cols-1 gap-0.5 min-[840px]:grid-cols-[88px_minmax(0,1fr)]">
                  <dt className="text-xs font-bold text-muted-text">Chunk terindeks</dt>
                  <dd className="text-[13px] text-tinta">
                    {document.chunk_count} segmen siap di-retrieval
                  </dd>
                </div>
              ) : null}
            </dl>
          </article>
          <article className="border-t border-[#dce4df] py-[22px]">
            <h2 className="mb-3 text-base font-bold text-tinta">Source viewer</h2>
            {document.available_chunks?.length ? (
              <ul className="m-0 grid list-none gap-2.5 p-0">
                {document.available_chunks.map((chunk) => (
                  <li
                    key={chunk.chunk_id}
                    className="rounded-md border border-[#dce4df] bg-[linear-gradient(#fff,#fbfdfd)] p-5"
                  >
                    <FileIcon className="size-[18px] [stroke-width:1.8] mb-2.5 text-javanese" />
                    <strong className="block text-[13px] text-tinta">{chunk.article}</strong>
                    <small className="block text-xs text-muted-text">
                      {chunk.paragraph ? `${chunk.paragraph} · ` : ""}
                      Halaman {chunk.page_start}
                      {chunk.page_end !== chunk.page_start ? `-${chunk.page_end}` : ""}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="rounded-md border border-[#dce4df] bg-[linear-gradient(#fff,#fbfdfd)] p-7">
                <FileIcon className="mb-5 size-7 [stroke-width:1.8] text-javanese" />
                <p className="m-0 leading-[1.8] text-tinta">
                  Dokumen belum terindeks — jalankan ingestion dari panel admin.
                </p>
              </div>
            )}
          </article>
        </div>
      </section>
    </AppShell>
  );
}
