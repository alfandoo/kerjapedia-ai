"use client";

import Link from "next/link";
import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { AlertIcon, CheckIcon, MoreIcon, RefreshIcon, SearchIcon, UploadIcon } from "./icons";
import {
  createIngestionJob,
  fetchAdminOverview,
  updateAdminDocument,
  updateAdminPublication,
  updateAdminRelationships,
} from "@/lib/api";
import { fallbackAdminDocuments } from "@/lib/sample-data";
import type { AdminDocument, AdminRelationship } from "@/lib/types";

const ingestionLabels: Record<AdminDocument["ingestion_status"], string> = {
  completed: "Selesai",
  needs_review: "Perlu review",
  failed: "Gagal",
  running: "Berjalan",
  queued: "Antre",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

type InspectorProps = {
  document: AdminDocument;
  allDocuments: AdminDocument[];
  onChange: (document: AdminDocument) => void;
  onClose: () => void;
};

function DocumentInspector({ document, allDocuments, onChange, onClose }: InspectorProps) {
  const [activeTab, setActiveTab] = useState<"metadata" | "relasi" | "versi">("metadata");
  const [legalStatus, setLegalStatus] = useState(document.legal_status);
  const [verificationStatus, setVerificationStatus] = useState(document.verification_status);
  const [topics, setTopics] = useState(document.topics.join(", "));
  const [relationshipTarget, setRelationshipTarget] = useState(
    allDocuments.find((item) => item.document_id !== document.document_id)?.document_id ?? ""
  );
  const [message, setMessage] = useState<string | null>(null);

  async function saveMetadata() {
    const nextTopics = topics
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const next = {
      ...document,
      legal_status: legalStatus,
      verification_status: verificationStatus,
      topics: nextTopics,
    };
    onChange(next);
    try {
      await updateAdminDocument(document.document_id, {
        legal_status: legalStatus,
        verification_status: verificationStatus,
        topics: nextTopics,
      });
      setMessage("Metadata berhasil disimpan.");
    } catch {
      setMessage("Metadata disimpan lokal; API belum tersedia.");
    }
  }

  async function addRelationship() {
    if (!relationshipTarget) return;
    const relationship: AdminRelationship = {
      from_document_id: document.document_id,
      to_document_id: relationshipTarget,
      relationship_type: "amended_by",
      confidence: "medium",
      notes: "Perlu verifikasi admin.",
    };
    const relationships = [...document.relationships, relationship];
    onChange({ ...document, relationships });
    try {
      await updateAdminRelationships(
        document.document_id,
        relationships.map((item) => ({
          to_document_id: item.to_document_id,
          relationship_type: item.relationship_type,
          confidence: item.confidence,
          notes: item.notes,
        }))
      );
      setMessage("Relasi berhasil diperbarui.");
    } catch {
      setMessage("Relasi disimpan lokal; API belum tersedia.");
    }
  }

  async function changePublication() {
    const action = document.publication_status === "published" ? "unpublish" : "publish";
    const nextStatus = action === "publish" ? "published" : "draft";
    const nextVersion = document.version + 1;
    const next = {
      ...document,
      publication_status: nextStatus as AdminDocument["publication_status"],
      version: nextVersion,
      versions: [
        {
          version: nextVersion,
          status: nextStatus as "draft" | "published",
          created_at: new Date().toISOString(),
          created_by: "Admin",
        },
        ...document.versions,
      ],
    };
    onChange(next);
    try {
      await updateAdminPublication(document.document_id, action);
      setMessage(action === "publish" ? "Dokumen diterbitkan." : "Penerbitan dibatalkan.");
    } catch {
      setMessage("Status publikasi diperbarui lokal; API belum tersedia.");
    }
  }

  async function reingest() {
    onChange({ ...document, ingestion_status: "running" });
    try {
      const job = await createIngestionJob(document.document_id);
      onChange({ ...document, ingestion_status: job.status });
      setMessage(`Re-ingest selesai dengan status ${job.status}.`);
    } catch {
      onChange({ ...document, ingestion_status: "queued" });
      setMessage("Re-ingest masuk antrean lokal; API belum tersedia.");
    }
  }

  return (
    <aside className="admin-inspector" aria-label={`Editor ${document.short_title}`}>
      <div className="inspector-heading">
        <div>
          <small>Dokumen terpilih</small>
          <h2>{document.short_title}</h2>
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label="Tutup inspector"
        >
          ×
        </button>
      </div>
      <div className="inspector-tabs" role="tablist" aria-label="Editor dokumen">
        {(["metadata", "relasi", "versi"] as const).map((tab) => (
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            className={activeTab === tab ? "active" : ""}
            onClick={() => setActiveTab(tab)}
            key={tab}
          >
            {tab[0].toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {activeTab === "metadata" ? (
        <div className="inspector-form">
          <label>
            Judul singkat
            <input value={document.short_title} readOnly />
          </label>
          <label>
            Status hukum
            <select value={legalStatus} onChange={(event) => setLegalStatus(event.target.value)}>
              <option value="active">Berlaku</option>
              <option value="needs_verification">Perlu verifikasi</option>
              <option value="historical">Historis</option>
              <option value="revoked">Dicabut</option>
            </select>
          </label>
          <label>
            Status verifikasi
            <select
              value={verificationStatus}
              onChange={(event) => setVerificationStatus(event.target.value)}
            >
              <option value="verified">Terverifikasi</option>
              <option value="pending_detail_url">Menunggu URL detail</option>
              <option value="needs_review">Perlu review</option>
            </select>
          </label>
          <label>
            Topik
            <input value={topics} onChange={(event) => setTopics(event.target.value)} />
          </label>
          <button
            type="button"
            className="admin-primary-button"
            onClick={() => void saveMetadata()}
          >
            Simpan perubahan
          </button>
        </div>
      ) : null}

      {activeTab === "relasi" ? (
        <div className="relationship-editor">
          {document.relationships.length ? (
            document.relationships.map((relationship) => (
              <div
                className="relationship-row"
                key={`${relationship.relationship_type}-${relationship.to_document_id}`}
              >
                <span>
                  <strong>{relationship.relationship_type.replaceAll("_", " ")}</strong>
                  <small>{relationship.to_document_id}</small>
                </span>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Hapus relasi ${relationship.to_document_id}`}
                  onClick={() =>
                    onChange({
                      ...document,
                      relationships: document.relationships.filter((item) => item !== relationship),
                    })
                  }
                >
                  ×
                </button>
              </div>
            ))
          ) : (
            <p className="admin-empty-copy">Belum ada relasi hukum untuk dokumen ini.</p>
          )}
          <label>
            Tambah relasi diubah oleh
            <select
              value={relationshipTarget}
              onChange={(event) => setRelationshipTarget(event.target.value)}
            >
              {allDocuments
                .filter((item) => item.document_id !== document.document_id)
                .map((item) => (
                  <option key={item.document_id} value={item.document_id}>
                    {item.short_title}
                  </option>
                ))}
            </select>
          </label>
          <button
            type="button"
            className="admin-secondary-button"
            onClick={() => void addRelationship()}
          >
            Tambah relasi
          </button>
        </div>
      ) : null}

      {activeTab === "versi" ? (
        <div className="version-list">
          {document.versions.map((version) => (
            <div className="version-row" key={`${version.version}-${version.created_at}`}>
              <span className="version-number">v{version.version}</span>
              <span>
                <strong>{version.status === "published" ? "Terbit" : "Draft"}</strong>
                <small>
                  {formatDate(version.created_at)} oleh {version.created_by}
                </small>
              </span>
              {version.version === document.version ? (
                <span className="status-badge success">Aktif</span>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      <div className={document.last_error ? "parsing-log warning" : "parsing-log success"}>
        {document.last_error ? <AlertIcon className="icon" /> : <CheckIcon className="icon" />}
        <span>
          <strong>
            {document.last_error ? "Log parsing perlu ditinjau" : "Parsing tanpa error"}
          </strong>
          <small>{document.last_error ?? `${document.chunk_count} chunk siap digunakan.`}</small>
        </span>
      </div>

      <div className="inspector-actions">
        <button type="button" className="admin-secondary-button" onClick={() => void reingest()}>
          <RefreshIcon className="icon" /> Re-ingest
        </button>
        <button
          type="button"
          className="admin-secondary-button"
          onClick={() => void changePublication()}
        >
          {document.publication_status === "published" ? "Batalkan terbit" : "Terbitkan"}
        </button>
        <button type="button" className="icon-button" aria-label="Aksi dokumen lainnya">
          <MoreIcon className="icon" />
        </button>
      </div>
      {message ? (
        <p className="admin-inline-message" role="status">
          {message}
        </p>
      ) : null}
    </aside>
  );
}

export function AdminDashboard() {
  const [documents, setDocuments] = useState(fallbackAdminDocuments);
  const [selectedId, setSelectedId] = useState<string | null>(
    fallbackAdminDocuments[0].document_id
  );
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [publicationFilter, setPublicationFilter] = useState("all");
  const [loadStatus, setLoadStatus] = useState("Memuat data admin...");
  const deferredSearch = useDeferredValue(search.toLowerCase());

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminOverview(controller.signal)
      .then((overview) => {
        setDocuments(overview.documents);
        setSelectedId(overview.documents[0]?.document_id ?? null);
        setLoadStatus("Data tersinkron dengan API.");
      })
      .catch(() => setLoadStatus("Menampilkan data contoh karena API belum tersedia."));
    return () => controller.abort();
  }, []);

  const filteredDocuments = useMemo(
    () =>
      documents.filter((document) => {
        const matchesSearch =
          `${document.short_title} ${document.title} ${document.topics.join(" ")}`
            .toLowerCase()
            .includes(deferredSearch);
        const matchesStatus = statusFilter === "all" || document.ingestion_status === statusFilter;
        const matchesPublication =
          publicationFilter === "all" || document.publication_status === publicationFilter;
        return matchesSearch && matchesStatus && matchesPublication;
      }),
    [deferredSearch, documents, publicationFilter, statusFilter]
  );

  const summary = useMemo(
    () => ({
      documents: documents.length,
      published: documents.filter((item) => item.publication_status === "published").length,
      needsReview: documents.filter((item) => item.ingestion_status === "needs_review").length,
      failed: documents.filter((item) => item.ingestion_status === "failed").length,
    }),
    [documents]
  );
  const selectedDocument = documents.find((item) => item.document_id === selectedId) ?? null;

  function replaceDocument(next: AdminDocument) {
    setDocuments((current) =>
      current.map((item) => (item.document_id === next.document_id ? next : item))
    );
  }

  return (
    <div
      className={
        selectedDocument ? "admin-document-workspace has-inspector" : "admin-document-workspace"
      }
    >
      <section className="admin-content-area">
        <div className="admin-page-heading">
          <div>
            <h1>Knowledge Base</h1>
            <p>{loadStatus}</p>
          </div>
          <Link href="/admin/upload" className="admin-primary-button">
            <UploadIcon className="icon" /> Upload dokumen
          </Link>
        </div>

        <div className="admin-summary-strip" aria-label="Ringkasan knowledge base">
          <div>
            <strong>{summary.documents}</strong>
            <span>Dokumen</span>
            <small>Total regulasi</small>
          </div>
          <div>
            <strong>{summary.published}</strong>
            <span>Terbit</span>
            <small>Sudah dipublikasikan</small>
          </div>
          <div className="warning">
            <strong>{summary.needsReview}</strong>
            <span>Review</span>
            <small>Perlu ditinjau</small>
          </div>
          <div className="danger">
            <strong>{summary.failed}</strong>
            <span>Gagal</span>
            <small>Ingestion error</small>
          </div>
        </div>

        <div className="admin-table-toolbar">
          <label className="admin-search-field">
            <SearchIcon className="icon" />
            <span className="sr-only">Cari dokumen</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Cari dokumen..."
            />
          </label>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            aria-label="Filter status ingestion"
          >
            <option value="all">Semua status</option>
            <option value="completed">Selesai</option>
            <option value="needs_review">Perlu review</option>
            <option value="failed">Gagal</option>
          </select>
          <select
            value={publicationFilter}
            onChange={(event) => setPublicationFilter(event.target.value)}
            aria-label="Filter publikasi"
          >
            <option value="all">Semua publikasi</option>
            <option value="published">Terbit</option>
            <option value="draft">Draft</option>
          </select>
        </div>

        <div
          className="admin-document-table"
          role="table"
          aria-label="Daftar dokumen knowledge base"
        >
          <div className="admin-document-row table-header" role="row">
            <span>Dokumen</span>
            <span>Topik</span>
            <span>Ingestion</span>
            <span>Publikasi</span>
            <span>Versi</span>
            <span>Diperbarui</span>
            <span></span>
          </div>
          {filteredDocuments.map((document) => (
            <div
              className={
                document.document_id === selectedId
                  ? "admin-document-row selected"
                  : "admin-document-row"
              }
              role="row"
              key={document.document_id}
            >
              <span>
                <strong>{document.short_title}</strong>
                <small>
                  {document.regulation_type} · {document.year}
                </small>
              </span>
              <span className="topic-cell">{document.topics[0]?.replaceAll("_", " ") ?? "-"}</span>
              <span>
                <i className={`status-dot ${document.ingestion_status}`} />
                {ingestionLabels[document.ingestion_status]}
              </span>
              <span>{document.publication_status === "published" ? "Terbit" : "Draft"}</span>
              <span>v{document.version}</span>
              <span>
                <strong>{formatDate(document.updated_at)}</strong>
                <small>oleh {document.updated_by}</small>
              </span>
              <span>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Edit ${document.short_title}`}
                  onClick={() => setSelectedId(document.document_id)}
                >
                  <MoreIcon className="icon" />
                </button>
              </span>
            </div>
          ))}
          {filteredDocuments.length === 0 ? (
            <p className="admin-empty-copy">Tidak ada dokumen yang cocok dengan filter.</p>
          ) : null}
        </div>
        <p className="admin-result-count">
          Menampilkan {filteredDocuments.length} dari {documents.length} dokumen
        </p>
      </section>

      {selectedDocument ? (
        <DocumentInspector
          key={selectedDocument.document_id}
          document={selectedDocument}
          allDocuments={documents}
          onChange={replaceDocument}
          onClose={() => setSelectedId(null)}
        />
      ) : null}
    </div>
  );
}
