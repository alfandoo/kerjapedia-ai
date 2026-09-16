"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, FileText, RefreshCw, Search, Upload, X } from "lucide-react";
import { Toaster } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState, PageHeader, StatusBadge } from "./primitives";
import { cn } from "@/lib/utils";
import { clearStoredSession, fetchAdminOverview } from "@/features/admin/api";
import styles from "./admin-documents.module.css";
import detailStyles from "./document-detail.module.css";
import type { AdminDocument } from "@/features/admin/types";

import {
  DocumentInspector,
  formatDate,
  ingestionLabels,
  ingestionTone,
} from "./document-inspector";

const PAGE_SIZE = 10;

function DocumentsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-[88px] rounded-xl" />
        ))}
      </div>
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-56" />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Skeleton className="h-10 flex-1" />
            <Skeleton className="h-10 w-[150px]" />
            <Skeleton className="h-10 w-[150px]" />
          </div>
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-16 w-full rounded-lg" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function AdminDashboard() {
  const router = useRouter();
  const [documents, setDocuments] = useState<AdminDocument[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [publicationFilter, setPublicationFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminOverview(controller.signal)
      .then((overview) => {
        setDocuments(overview.documents);
        setLoadError(null);
        setIsLoading(false);
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const message = (err as Error).message || "";
        if (/token|bearer/i.test(message)) {
          clearStoredSession();
          router.push("/login-admin");
          return;
        }
        setLoadError("Daftar dokumen belum dapat dimuat. Periksa koneksi lalu coba lagi.");
        setIsLoading(false);
      });
    return () => controller.abort();
  }, [router, reloadKey]);

  const filteredDocuments = useMemo(
    () =>
      documents.filter((document) => {
        const matchesSearch =
          `${document.document_id} ${document.short_title} ${document.title} ${document.regulation_type} ${document.year} ${document.topics.join(" ")}`
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

  const totalPages = Math.max(1, Math.ceil(filteredDocuments.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pagedDocuments = filteredDocuments.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const rangeStart = filteredDocuments.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(safePage * PAGE_SIZE, filteredDocuments.length);

  function goToPage(next: number) {
    setPage(Math.min(Math.max(1, next), totalPages));
  }

  function replaceDocument(next: AdminDocument) {
    setDocuments((current) =>
      current.map((item) => (item.document_id === next.document_id ? next : item))
    );
  }

  const summaryCells = [
    {
      label: "Dokumen",
      value: summary.documents,
      note: "Total regulasi",
      dot: "bg-javanese/50",
      tone: "text-tinta",
    },
    {
      label: "Terbit",
      value: summary.published,
      note: "Sudah dipublikasikan",
      dot: "bg-forest",
      tone: "text-tinta",
    },
    {
      label: "Review",
      value: summary.needsReview,
      note: "Perlu ditinjau",
      dot: "bg-amber",
      tone: "text-amber",
    },
    {
      label: "Gagal",
      value: summary.failed,
      note: "Pemrosesan gagal",
      dot: "bg-red",
      tone: "text-red",
    },
  ];

  return (
    <div className={`${styles.documents} space-y-6`}>
      <Toaster position="bottom-right" richColors />

      {isLoading ? (
        <div role="status" aria-label="Memuat dokumen">
          <DocumentsSkeleton />
        </div>
      ) : loadError ? (
        <div role="alert" className={styles.loadError}>
          <EmptyState
            icon={FileText}
            title="Dokumen tidak dapat dimuat"
            hint={loadError}
            action={
              <Button
                type="button"
                variant="outline"
                className="min-h-11"
                onClick={() => {
                  setLoadError(null);
                  setIsLoading(true);
                  setReloadKey((value) => value + 1);
                }}
              >
                <RefreshCw /> Coba lagi
              </Button>
            }
          />
        </div>
      ) : (
        <>
          <PageHeader
            eyebrow="Regulasi ketenagakerjaan"
            title="Dokumen"
            description="Kelola dokumen regulasi yang menjadi sumber jawaban KerjaPedia AI."
            actions={
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="h-11"
                  aria-label="Muat ulang daftar dokumen"
                  onClick={() => {
                    setIsLoading(true);
                    setReloadKey((value) => value + 1);
                  }}
                >
                  <RefreshCw /> Muat ulang
                </Button>
                <Button
                  asChild
                  className="h-11 bg-javanese px-5 text-sm font-bold text-white shadow-[0_2px_12px_rgba(27,67,50,0.22)] hover:bg-javanese-deep"
                >
                  <Link href="/admin/upload">
                    <Upload strokeWidth={2} /> Upload dokumen
                  </Link>
                </Button>
              </div>
            }
          />

          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line lg:grid-cols-4">
            {summaryCells.map((cell) => {
              const active =
                cell.label === "Dokumen"
                  ? statusFilter === "all" && publicationFilter === "all"
                  : cell.label === "Terbit"
                    ? publicationFilter === "published" && statusFilter === "all"
                    : statusFilter === (cell.label === "Gagal" ? "failed" : "needs_review") &&
                      publicationFilter === "all";
              return (
                <button
                  key={cell.label}
                  type="button"
                  aria-pressed={active}
                  onClick={() => {
                    setStatusFilter(
                      cell.label === "Gagal"
                        ? "failed"
                        : cell.label === "Review"
                          ? "needs_review"
                          : "all"
                    );
                    setPublicationFilter(cell.label === "Terbit" ? "published" : "all");
                    setSearch("");
                    setPage(1);
                  }}
                  className={cn(
                    "flex flex-col items-start gap-0.5 bg-white px-5 py-4 text-left",
                    styles.summary,
                    active && styles.summaryActive
                  )}
                >
                  <p className="flex items-center gap-1.5 font-mono text-xl font-bold text-tinta tabular-nums">
                    <span aria-hidden="true" className={cn("size-1.5 rounded-full", cell.dot)} />
                    <span className={cell.tone}>{cell.value}</span>
                  </p>
                  <p className="text-sm font-medium">{cell.label}</p>
                  <p className="text-xs text-muted-text">{cell.note}</p>
                </button>
              );
            })}
          </div>

          <Card>
            <CardHeader className="flex flex-wrap items-start justify-between gap-3 space-y-0">
              <div className="space-y-1.5">
                <CardTitle>Daftar dokumen</CardTitle>
                <CardDescription>
                  Menampilkan {filteredDocuments.length} dari {documents.length} dokumen
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative min-w-0 basis-full sm:min-w-56 sm:flex-1 sm:basis-auto">
                  <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-text" />
                  <Input
                    value={search}
                    onChange={(event) => {
                      setSearch(event.target.value);
                      setPage(1);
                    }}
                    placeholder="Cari judul, nomor, topik..."
                    aria-label="Cari dokumen"
                    className="h-11 pl-8"
                  />
                </div>
                <Select
                  value={statusFilter}
                  onValueChange={(value) => {
                    setStatusFilter(value);
                    setPage(1);
                  }}
                >
                  <SelectTrigger
                    aria-label="Filter status pemrosesan"
                    className="h-11 w-full sm:w-[170px]"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Semua status</SelectItem>
                    <SelectItem value="completed">Selesai</SelectItem>
                    <SelectItem value="queued">Antre</SelectItem>
                    <SelectItem value="running">Diproses</SelectItem>
                    <SelectItem value="needs_review">Perlu review</SelectItem>
                    <SelectItem value="failed">Gagal</SelectItem>
                  </SelectContent>
                </Select>
                <Select
                  value={publicationFilter}
                  onValueChange={(value) => {
                    setPublicationFilter(value);
                    setPage(1);
                  }}
                >
                  <SelectTrigger aria-label="Filter publikasi" className="h-11 w-full sm:w-[170px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Semua publikasi</SelectItem>
                    <SelectItem value="published">Terbit</SelectItem>
                    <SelectItem value="draft">Draft</SelectItem>
                  </SelectContent>
                </Select>
                {search || statusFilter !== "all" || publicationFilter !== "all" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="min-h-11"
                    onClick={() => {
                      setSearch("");
                      setStatusFilter("all");
                      setPublicationFilter("all");
                      setPage(1);
                    }}
                  >
                    <X /> Reset
                  </Button>
                ) : null}
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Dokumen</TableHead>
                    <TableHead>Topik</TableHead>
                    <TableHead>Pemrosesan</TableHead>
                    <TableHead>Publikasi</TableHead>
                    <TableHead>Versi</TableHead>
                    <TableHead>Diperbarui</TableHead>
                    <TableHead className="w-14">
                      <span className="sr-only">Tindakan</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pagedDocuments.map((document) => (
                    <TableRow
                      key={document.document_id}
                      className="group cursor-pointer"
                      onClick={() => setSelectedId(document.document_id)}
                    >
                      <TableCell className="max-w-64">
                        <button
                          type="button"
                          className={styles.documentTitle}
                          title={document.title}
                          aria-label={`Lihat detail ${document.short_title}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelectedId(document.document_id);
                          }}
                        >
                          {document.short_title}
                        </button>
                        <span className="block font-mono text-xs text-muted-text">
                          {document.regulation_type} · {document.year}
                        </span>
                      </TableCell>
                      <TableCell>
                        {document.topics[0] ? (
                          <span className="flex items-center gap-1.5">
                            <Badge variant="secondary">
                              {document.topics[0].replaceAll("_", " ")}
                            </Badge>
                            {document.topics.length > 1 ? (
                              <span className="text-xs text-muted-text">
                                +{document.topics.length - 1}
                              </span>
                            ) : null}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-text">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <StatusBadge tone={ingestionTone[document.ingestion_status]}>
                          {ingestionLabels[document.ingestion_status]}
                        </StatusBadge>
                      </TableCell>
                      <TableCell>
                        {document.publication_status === "published" ? (
                          <StatusBadge tone="success">Terbit</StatusBadge>
                        ) : (
                          <StatusBadge tone="neutral">Draft</StatusBadge>
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-xs">v{document.version}</TableCell>
                      <TableCell className="text-xs">
                        <span className="block text-muted-text">
                          {formatDate(document.updated_at)}
                        </span>
                        {document.updated_by ? (
                          <span className="block text-muted-text">oleh {document.updated_by}</span>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Buka ${document.short_title}`}
                          className="size-11 text-forest"
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelectedId(document.document_id);
                          }}
                        >
                          <ChevronRight className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {filteredDocuments.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7}>
                        <EmptyState
                          icon={FileText}
                          title={
                            documents.length === 0
                              ? "Belum ada dokumen"
                              : "Tidak ada dokumen yang cocok"
                          }
                          hint={
                            documents.length === 0
                              ? "Unggah PDF pertama untuk menyiapkan sumber jawaban."
                              : "Coba kata kunci lain atau hapus filter yang dipilih."
                          }
                          action={
                            documents.length === 0 ? (
                              <Button asChild className="min-h-11">
                                <Link href="/admin/upload">
                                  <Upload /> Upload dokumen
                                </Link>
                              </Button>
                            ) : (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="min-h-11"
                                onClick={() => {
                                  setSearch("");
                                  setStatusFilter("all");
                                  setPublicationFilter("all");
                                  setPage(1);
                                }}
                              >
                                <X /> Reset filter
                              </Button>
                            )
                          }
                        />
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>

              {filteredDocuments.length > 0 ? (
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
                  <p className="text-xs text-muted-text tabular-nums">
                    Menampilkan {rangeStart} sampai {rangeEnd} dari {filteredDocuments.length}{" "}
                    dokumen
                  </p>
                  {totalPages > 1 ? (
                    <nav aria-label="Navigasi halaman" className="flex items-center gap-1">
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-sm"
                        className="size-11"
                        disabled={safePage === 1}
                        aria-label="Halaman sebelumnya"
                        onClick={() => goToPage(safePage - 1)}
                      >
                        <ChevronLeft className="size-4" />
                      </Button>
                      <span
                        aria-live="polite"
                        className="px-3 text-xs tabular-nums text-muted-text"
                      >
                        Halaman {safePage} dari {totalPages}
                      </span>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-sm"
                        className="size-11"
                        disabled={safePage === totalPages}
                        aria-label="Halaman berikutnya"
                        onClick={() => goToPage(safePage + 1)}
                      >
                        <ChevronRight className="size-4" />
                      </Button>
                    </nav>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Sheet
            open={selectedDocument !== null}
            onOpenChange={(open) => {
              if (!open) setSelectedId(null);
            }}
          >
            <SheetContent
              side="center"
              className={`${detailStyles.modal} w-full sm:max-w-lg`}
              showCloseButton={false}
            >
              {selectedDocument ? (
                <DocumentInspector
                  key={selectedDocument.document_id}
                  document={selectedDocument}
                  allDocuments={documents}
                  onChange={replaceDocument}
                  onClose={() => setSelectedId(null)}
                />
              ) : null}
            </SheetContent>
          </Sheet>
        </>
      )}
    </div>
  );
}
