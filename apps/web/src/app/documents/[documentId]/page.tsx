import Link from "next/link";
import { notFound } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { ExternalIcon, FileIcon } from "@/components/icons";
import { documentPdfUrl, fetchDocumentDetail } from "@/features/documents/api";
import { fallbackCitation } from "@/features/chat";
import { fallbackDocuments } from "@/features/documents";

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
  available_chunks: {
    chunk_id: string;
    article: string;
    paragraph: string;
    page_start: number;
    page_end: number;
  }[];
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
      <section className="mx-auto w-full min-w-0 max-w-[1080px]">
        <Link
          href="/search"
          className="mb-5 inline-flex min-h-11 items-center gap-2.5 rounded-md text-sm font-bold text-javanese transition hover:text-forest focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese"
        >
          Kembali ke pencarian
        </Link>
        <div className="mb-6 min-w-0">
          <h1 className="font-display text-balance break-words text-[clamp(28px,7vw,50px)] font-medium leading-[1.12] tracking-[-0.035em] text-javanese">
            {document.title}
          </h1>
          <p className="mt-1.5 break-words text-sm leading-[1.75] text-muted-text">
            {document.regulation_type} Nomor {document.number} Tahun {document.year}
          </p>
        </div>
        {fromFallback ? (
          <p
            className="-mt-2 mb-6 block break-words rounded-r-md border-l-[3px] border-[#bc8121] bg-[#fffaf0] px-3.5 py-2.5 text-xs leading-relaxed text-[#6e531c]"
            role="status"
          >
            API detail belum tersedia. Menampilkan data katalog referensi lokal sementara.
          </p>
        ) : null}
        <div className="grid min-w-0 grid-cols-1 gap-4 min-[840px]:grid-cols-[320px_minmax(0,1fr)]">
          <article className="min-w-0 border-t border-[#e5e5e5] py-[22px]">
            <h2 className="mb-3 text-base font-bold text-tinta">Metadata</h2>
            <dl className="my-4 grid gap-2.5">
              <div className="grid min-w-0 grid-cols-1 gap-0.5 min-[840px]:grid-cols-[88px_minmax(0,1fr)]">
                <dt className="text-xs font-bold text-muted-text">Status hukum</dt>
                <dd className="min-w-0 break-words text-[13px] text-tinta">
                  {formatStatus(document.legal_status)}
                </dd>
              </div>
              <div className="grid min-w-0 grid-cols-1 gap-0.5 min-[840px]:grid-cols-[88px_minmax(0,1fr)]">
                <dt className="text-xs font-bold text-muted-text">Topik</dt>
                <dd className="min-w-0 break-words text-[13px] text-tinta">
                  {document.topics.map((item) => item.replaceAll("_", " ")).join(", ")}
                </dd>
              </div>
              <div className="grid min-w-0 grid-cols-1 gap-0.5 min-[840px]:grid-cols-[88px_minmax(0,1fr)]">
                <dt className="text-xs font-bold text-muted-text">Sumber</dt>
                <dd className="min-w-0 break-words text-[13px] text-tinta">
                  <a
                    href={document.source_url || documentPdfUrl(document.document_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex min-h-11 items-center break-words text-javanese underline decoration-javanese/40 underline-offset-4 transition hover:text-forest focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese"
                  >
                    {document.source_name || "Buka sumber resmi"}
                    <ExternalIcon className="size-[18px] [stroke-width:1.8] ml-1 inline-block shrink-0 align-[-3px]" />
                  </a>
                </dd>
              </div>
              <div className="grid min-w-0 grid-cols-1 gap-0.5 min-[840px]:grid-cols-[88px_minmax(0,1fr)]">
                <dt className="text-xs font-bold text-muted-text">Berkas asli</dt>
                <dd className="min-w-0 break-words text-[13px] text-tinta">
                  <a
                    href={documentPdfUrl(document.document_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex min-h-11 items-center break-words text-javanese underline decoration-javanese/40 underline-offset-4 transition hover:text-forest focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-javanese"
                  >
                    {document.file_name || "Buka PDF dataset"}
                    <ExternalIcon className="size-[18px] [stroke-width:1.8] ml-1 inline-block shrink-0 align-[-3px]" />
                  </a>
                </dd>
              </div>
              {document.chunk_count > 0 ? (
                <div className="grid min-w-0 grid-cols-1 gap-0.5 min-[840px]:grid-cols-[88px_minmax(0,1fr)]">
                  <dt className="text-xs font-bold text-muted-text">Segmen terindeks</dt>
                  <dd className="min-w-0 break-words text-[13px] text-tinta">
                    {document.chunk_count} segmen siap untuk retrieval
                  </dd>
                </div>
              ) : null}
            </dl>
          </article>
          <article className="min-w-0 border-t border-[#e5e5e5] py-[22px]">
            <h2 className="mb-3 text-base font-bold text-tinta">Cuplikan sumber</h2>
            {document.available_chunks?.length ? (
              <ul className="m-0 grid list-none gap-2.5 p-0">
                {document.available_chunks.map((chunk) => (
                  <li
                    key={chunk.chunk_id}
                    className="min-w-0 rounded-md border border-[#e5e5e5] bg-card p-5"
                  >
                    <FileIcon className="size-[18px] [stroke-width:1.8] mb-2.5 text-javanese" />
                    <strong className="block break-words text-[13px] text-tinta">
                      {chunk.article}
                    </strong>
                    <small className="block break-words text-xs text-muted-text">
                      {chunk.paragraph ? `${chunk.paragraph} · ` : ""}
                      Halaman {chunk.page_start}
                      {chunk.page_end !== chunk.page_start ? `-${chunk.page_end}` : ""}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="rounded-md border border-[#e5e5e5] bg-card p-5">
                <FileIcon className="mb-5 size-7 [stroke-width:1.8] text-javanese" />
                <p className="m-0 break-words leading-[1.8] text-tinta">
                  Dokumen belum terindeks. Jalankan ingestion dari panel admin.
                </p>
              </div>
            )}
          </article>
        </div>
      </section>
    </AppShell>
  );
}
