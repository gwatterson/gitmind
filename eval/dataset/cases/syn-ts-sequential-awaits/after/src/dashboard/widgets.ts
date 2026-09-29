import { api } from "../api";

export interface Widget {
  id: string;
  data: unknown;
}

export async function loadWidgets(ids: string[]): Promise<Widget[]> {
  const widgets: Widget[] = [];
  for (const id of ids) {
    const data = await api.get(`/widgets/${id}`);
    widgets.push({ id, data });
  }
  return widgets;
}
