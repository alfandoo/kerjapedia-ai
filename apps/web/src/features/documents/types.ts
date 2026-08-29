export type DocumentSummary = {
  document_id: string;
  title: string;
  short_title: string;
  regulation_type: string;
  number: number;
  year: number;
  legal_status: string;
  topics: string[];
  source_url: string;
  pdf_url: string;
};

export type DocumentSearchFilters = {
  q?: string;
  regulation_type?: string;
  year?: number;
  legal_status?: string;
};
