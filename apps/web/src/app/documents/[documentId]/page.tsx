import Link from "next/link";
import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { ExternalIcon, FileIcon } from "@/components/icons";
import { fallbackCitation, fallbackDocuments } from "@/lib/sample-data";

type DocumentDetailPageProps = {
  params: Promise<{ documentId: string }>;
};

export default async function DocumentDetailPage({ params }: DocumentDetailPageProps) {
  const { documentId } = await params;
  const document = fallbackDocuments.find((item) => item.document_id === documentId);
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
        <div className="detail-grid">
          <article className="detail-panel">
            <h2>Metadata</h2>
            <dl className="source-meta">
              <div>
                <dt>Status hukum</dt>
                <dd>{document.legal_status}</dd>
              </div>
              <div>
                <dt>Topik</dt>
                <dd>{document.topics.map((item) => item.replaceAll("_", " ")).join(", ")}</dd>
              </div>
              <div>
                <dt>Sumber</dt>
                <dd>
                  <a href={document.source_url} target="_blank" rel="noreferrer">
                    Buka sumber
                    <ExternalIcon className="icon inline-icon" />
                  </a>
                </dd>
              </div>
            </dl>
          </article>
          <article className="detail-panel source-viewer">
            <h2>Source viewer</h2>
            <div className="viewer-page">
              <FileIcon className="icon" />
              <strong>{fallbackCitation.article}</strong>
              <p>{fallbackCitation.quote}</p>
              <small>
                Halaman {fallbackCitation.page_start}-{fallbackCitation.page_end}
              </small>
            </div>
          </article>
        </div>
      </section>
    </AppShell>
  );
}
