export interface Notification {
  id: string;
  message: string;
  read: boolean;
}

export async function fetchNotifications(userId: string): Promise<Notification[]> {
  try {
    const response = await fetch(`/api/users/${userId}/notifications`);
    return (await response.json()) as Notification[];
  } catch (e) {}
  return [];
}
