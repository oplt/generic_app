import { apiFetch } from "../../../api/client";
import type { Order, OrderCreate, OrderUpdate } from "./types";

export async function listOrders(): Promise<Order[]> {
    return apiFetch("/orders");
}

export async function getOrder(id: string): Promise<Order> {
    return apiFetch(`/orders/${id}`);
}

export async function createOrder(
    payload: OrderCreate
): Promise<Order> {
    return apiFetch("/orders", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function updateOrder(
    id: string,
    payload: OrderUpdate
): Promise<Order> {
    return apiFetch(`/orders/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function deleteOrder(id: string): Promise<void> {
    await apiFetch(`/orders/${id}`, { method: "DELETE" });
}
