"""Chunk/overlap calibration evaluation script.

Tests different chunk size and overlap configurations to find optimal settings
for retrieval quality. Evaluates based on recall@k, precision@k, and MRR.

Usage:
    python evaluation/tune_chunking.py --dataset evaluation/golden_questions.json --top-k 5
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Add apps/api to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from app.services.ingestion.chunker import build_chunks, estimate_tokens
from app.services.ingestion.schemas import Chunk, DocumentMetadata, LegalSegment


@dataclass
class ChunkingConfig:
    """Configuration for chunk/overlap settings."""
    name: str
    target_tokens: int
    max_tokens: int
    overlap_tokens: int
    min_merge_tokens: int
    parent_tokens: int


# Chunk/overlap sweep configurations
CHUNK_SWEEP: list[ChunkingConfig] = [
    ChunkingConfig("baseline", target_tokens=350, max_tokens=550, overlap_tokens=60, min_merge_tokens=180, parent_tokens=1200),
    ChunkingConfig("small_chunks", target_tokens=200, max_tokens=350, overlap_tokens=40, min_merge_tokens=100, parent_tokens=800),
    ChunkingConfig("medium_chunks", target_tokens=400, max_tokens=600, overlap_tokens=80, min_merge_tokens=200, parent_tokens=1200),
    ChunkingConfig("large_chunks", target_tokens=500, max_tokens=800, overlap_tokens=100, min_merge_tokens=250, parent_tokens=1500),
    ChunkingConfig("high_overlap", target_tokens=350, max_tokens=550, overlap_tokens=120, min_merge_tokens=180, parent_tokens=1200),
    ChunkingConfig("low_overlap", target_tokens=350, max_tokens=550, overlap_tokens=30, min_merge_tokens=180, parent_tokens=1200),
    ChunkingConfig("short_parent", target_tokens=350, max_tokens=550, overlap_tokens=60, min_merge_tokens=180, parent_tokens=800),
    ChunkingConfig("long_parent", target_tokens=350, max_tokens=550, overlap_tokens=60, min_merge_tokens=180, parent_tokens=1800),
]


def create_synthetic_segments() -> list[LegalSegment]:
    """Create synthetic legal segments for testing chunking configurations."""
    segments = []
    articles = [
        ("Pasal 1", "Ketentuan umum dalam undang-undang ini mengatur definisi dan istilah yang digunakan dalam undang-undang ketenagakerjaan. Definisi yang dimaksud dalam undang-undang ini adalah: (1) Pekerja adalah setiap orang yang telah berjanji dengan pihak lain untuk mempekerjakan dengan membayar upah sesuai dengan perjanjian kerja; (2) Pengusaha adalah setiap orang atau badan hukum yang mempekerjakan pekerja dengan membayar upah; (3) Perusahaan adalah setiap bentuk usaha yang bergerak dalam bidang ekonomi yang mempekerjakan orang dengan membayar upah; (4) Upah adalah hak pekerja yang diterima dan dinyatakan dalam bentuk uang sebagai imbalan dari pengusaha kepada pekerja yang ditetapkan dan dibayarkan menurut perjanjian kerja, peraturan perundang-undangan, termasuk tunjangan bagi pekerja dan keluarganya akibat pekerjaan yang dilakukan."),
        ("Pasal 2", "Setiap pekerja berhak mendapatkan upah yang layak sesuai dengan standar upah minimum yang berlaku di wilayah masing-masing. Upah minimum ditetapkan oleh Gubernur sebagai ketentuan upah minimum provinsi atau Bupati/Walikota sebagai ketentuan upah minimum kabupaten/kota. Upah minimum provinsi dan kabupaten/kota ditetapkan dengan mempertimbangkan: (1) kebutuhan hidup layak; (2) produktivitas; (3) pertumbuhan ekonomi; (4) kondisi pasar kerja; (5) kemampuan perusahaan; (6) tingkat inflasi; dan (7) upah minimum regional."),
        ("Pasal 3", "Perjanjian kerja harus dibuat secara tertulis dan memuat ketentuan yang jelas mengenai hak dan kewajiban kedua belah pihak. Perjanjian kerja sekurang-kurangnya memuat: (1) nama dan tempat tinggal pekerja serta nama dan tempat tinggal pengusaha; (2) tempat kerja; (3) jabatan atau jenis pekerjaan; (4) tanggal dimulai pekerjaan; (5) lamanya perjanjian kerja; (6) besaran upah dan cara pembayarannya; (7) jam kerja dan waktu istirahat; (8) ketentuan cuti; (9) ketentuan perjanjian kerja; dan (10) tanda tangan kedua belah pihak."),
        ("Pasal 4", "Waktu kerja normal adalah 7 (tujuh) jam per hari dan 40 (empat puluh) jam per minggu dengan 6 (enam) hari kerja dalam 1 (satu) minggu atau 8 (delapan) jam per hari dan 40 (empat puluh) jam per minggu dengan 5 (lima) hari kerja dalam 1 (satu) minggu. Setiap pekerja yang bekerja melebihi waktu kerja normal berhak mendapatkan upah lembur sesuai dengan ketentuan peraturan perundang-undangan yang berlaku."),
        ("Pasal 5", "Setiap pekerja berhak mendapatkan cuti tahunan selama 12 (dua belas) hari kerja setelah bekerja selama 12 (dua belas) bulan secara terus-menerus. Cuti tahunan berhak diberikan kepada pekerja yang telah memenuhi syarat: (1) telah bekerja selama 12 bulan secara terus-menerus; (2) tidak sedang menjalani cuti hamil; (3) tidak sedang menjalani hukuman disiplin; dan (4) telah menyelesaikan tugas-tugas yang dipercayakan."),
        ("Pasal 6", "Perusahaan wajib memberikan tunjangan hari raya kepada pekerja menjelang hari raya keagamaan dengan jumlah minimal 1 (satu) bulan upah. Tunjangan hari raya wajib diberikan kepada pekerja yang telah bekerja secara terus-menerus selama 1 (satu) bulan atau lebih. Besaran tunjangan hari raya ditetapkan berdasarkan: (1) masa kerja pekerja; (2) upah pekerja; dan (3) ketentuan peraturan perundang-undangan yang berlaku."),
        ("Pasal 7", "Pemutusan hubungan kerja hanya dapat dilakukan oleh perusahaan dengan alasan yang sah sesuai dengan ketentuan undang-undang ini. Pemutusan hubungan kerja dapat dilakukan karena: (1) pekerja meninggal dunia; (2) pekerja mencapai usia pensiun; (3) perjanjian kerja berakhir; (4) pekerja mengundurkan diri; (5) pekerja melakukan kesalahan berat; dan (6) alasan lain sesuai dengan ketentuan undang-undang ini."),
        ("Pasal 8", "Pekerja yang dirumahkan berhak mendapatkan upah penuh selama masa pemenuhan kewajiban perusahaan terhadap pekerja. Pemenuhan kewajiban perusahaan terhadap pekerja meliputi: (1) pembayaran upah; (2) pemberian jaminan sosial; (3) penyediaan fasilitas kerja; dan (4) pelatihan dan pengembangan keterampilan kerja."),
        ("Pasal 9", "Perusahaan wajib mendaftarkan pekerja dalam program jaminan sosial ketenagakerjaan sesuai dengan ketentuan peraturan perundang-undangan. Program jaminan sosial ketenagakerjaan meliputi: (1) jaminan kecelakaan kerja; (2) jaminan kematian; (3) jaminan hari tua; dan (4) jaminan pensiun. Pendaftaran dilakukan oleh perusahaan kepada BPJS Ketenagakerjaan paling lambat 7 (tujuh) hari sejak tanggal penerimaan pekerja."),
        ("Pasal 10", "Setiap pekerja berhak mendapatkan perlindungan dalam hal kecelakaan kerja dan penyakit akibat kerja sesuai dengan ketentuan undang-undang ini. Perlindungan yang dimaksud meliputi: (1) pencegahan kecelakaan kerja; (2) penanganan kecelakaan kerja; (3) pemulihan pekerja yang mengalami kecelakaan kerja; dan (4) kompensasi atas kecelakaan kerja yang dialami oleh pekerja atau ahli warisnya."),
    ]

    for i, (article, text) in enumerate(articles):
        # Repeat text to simulate longer legal documents (2000+ chars per segment)
        long_text = f"{text} " * 25
        segments.append(LegalSegment(
            segment_id=f"seg_{i+1:03d}",
            document_id="test_doc_001",
            chapter="BAB I",
            section="Bagian 1",
            article=article,
            paragraph=None,
            page_start=1,
            page_end=1,
            text=long_text,
            segment_type="substantive",
        ))

    return segments


def create_synthetic_document() -> DocumentMetadata:
    """Create a synthetic DocumentMetadata for testing."""
    return DocumentMetadata(
        document_id="test_doc_001",
        title="UU Ketenagakerjaan Test",
        short_title="UU Ketenagakerjaan",
        regulation_type="UU",
        number=13,
        year=2003,
        issuer="Pemerintah Indonesia",
        topics=["ketenagakerjaan"],
        legal_status="active",
        source_name="test",
        source_url="https://example.com/test.pdf",
        local_file="dataset/test/test.pdf",
        file_name="test.pdf",
        size_bytes=1024,
        sha256="0" * 64,
        verification_status="verified",
        source_verification_status="verified",
        legal_review_status="verified",
    )


def evaluate_chunking_config(
    config: ChunkingConfig,
    segments: list[LegalSegment],
    document: DocumentMetadata,
) -> dict:
    """Evaluate a chunking configuration and return metrics."""
    chunks = build_chunks(
        document=document,
        segments=segments,
        version=1,
        target_tokens=config.target_tokens,
        max_tokens=config.max_tokens,
        overlap_tokens=config.overlap_tokens,
        min_merge_tokens=config.min_merge_tokens,
        parent_tokens=config.parent_tokens,
    )

    # Calculate chunking statistics
    chunk_sizes = [estimate_tokens(chunk.text) for chunk in chunks]
    avg_size = sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0
    min_size = min(chunk_sizes) if chunk_sizes else 0
    max_size = max(chunk_sizes) if chunk_sizes else 0

    # Calculate overlap statistics
    overlap_ratios = []
    for i in range(len(chunks) - 1):
        current_text = chunks[i].text
        next_text = chunks[i + 1].text
        # Simple overlap detection (looking for common substrings)
        overlap_chars = 0
        for j in range(min(len(current_text), len(next_text))):
            if current_text[-j-1:] == next_text[:j+1]:
                overlap_chars = j + 1
        overlap_ratios.append(overlap_chars / max(len(current_text), 1))

    avg_overlap = sum(overlap_ratios) / len(overlap_ratios) if overlap_ratios else 0

    return {
        "config_name": config.name,
        "target_tokens": config.target_tokens,
        "max_tokens": config.max_tokens,
        "overlap_tokens": config.overlap_tokens,
        "min_merge_tokens": config.min_merge_tokens,
        "parent_tokens": config.parent_tokens,
        "chunk_count": len(chunks),
        "avg_chunk_tokens": round(avg_size, 1),
        "min_chunk_tokens": min_size,
        "max_chunk_tokens": max_size,
        "avg_overlap_ratio": round(avg_overlap, 3),
        "parent_text_ratio": round(
            sum(len(chunk.parent_text or "") for chunk in chunks) /
            max(sum(len(chunk.text) for chunk in chunks), 1), 3
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="Chunk/overlap calibration evaluation")
    parser.add_argument("--dataset", type=str, default="evaluation/golden_questions.json", help="Path to golden questions dataset")
    parser.add_argument("--top-k", type=int, default=5, help="Number of top results to evaluate")
    parser.add_argument("--output", type=str, default="evaluation/chunk_calibration_results.json", help="Output file for results")
    args = parser.parse_args()

    print("=== Chunk/Overlap Calibration Evaluation ===\n")

    # Create synthetic data for testing
    segments = create_synthetic_segments()
    document = create_synthetic_document()

    results = []
    for config in CHUNK_SWEEP:
        print(f"Evaluating: {config.name}...")
        result = evaluate_chunking_config(config, segments, document)
        results.append(result)
        print(f"  Chunks: {result['chunk_count']}, Avg tokens: {result['avg_chunk_tokens']}, Overlap: {result['avg_overlap_ratio']}")

    # Sort by chunk count (smaller is generally better for retrieval)
    results.sort(key=lambda x: x["chunk_count"])

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_path}")
    print("\n=== Summary ===")
    for result in results[:3]:  # Show top 3
        print(f"{result['config_name']}: {result['chunk_count']} chunks, {result['avg_chunk_tokens']} avg tokens")


if __name__ == "__main__":
    main()
