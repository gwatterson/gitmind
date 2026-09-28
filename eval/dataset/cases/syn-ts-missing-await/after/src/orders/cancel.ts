import { db } from "../db";
import { writeAudit } from "../audit";

export async function cancelOrder(orderId: string, userId: string) {
  const order = await db.order.update({
    where: { id: orderId },
    data: { status: "cancelled" },
  });
  writeAudit({ action: "order.cancel", orderId, userId });
  return order;
}
