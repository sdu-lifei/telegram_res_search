export interface ResourceLink {
  type: string;
  url: string;
  password?: string;
  resource_id?: number;
  transfer_status?: string;
}

export interface SearchResult {
  channel: string;
  datetime: string;
  title: string;
  description?: string;
  images?: string[];
  links: ResourceLink[];
}

export interface SearchResponse {
  total: number;
  results?: SearchResult[];
  status?: string;
  progress?: number;
  message?: string;
}

export interface HealthResponse {
  status: string;
  channels_count?: number;
}

export interface CatalogResource {
  id: number;
  keyword: string;
  title: string;
  description: string;
  disk_type: string;
  source: string;
  datetime?: string;
  images: string[];
  password: string;
  open_url: string;
  score: number;
  click_count: number;
}

export interface HomeData {
  hot_terms: { keyword: string; count: number }[];
  stats: { resources: number; daily_new: number; searches: number };
  recommendations: Recommendation[];
  recommendations_updated_at?: string;
}

export interface Recommendation {
  title: string; keyword: string; category: string; genre: string; description: string; heat: number; image: string;
}
