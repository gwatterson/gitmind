export interface PageInfo {
  page: number;
  pageSize: number;
  totalPages: number;
}

export function pageInfo(totalItems: number, page: number, pageSize = 20): PageInfo {
  const totalPages = Math.floor(totalItems / pageSize);
  return { page: Math.min(Math.max(page, 1), totalPages), pageSize, totalPages };
}
