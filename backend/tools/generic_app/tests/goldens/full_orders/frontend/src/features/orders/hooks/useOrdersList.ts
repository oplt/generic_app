import { useQuery } from "@tanstack/react-query";

import { listOrders } from "../api";

export const ordersQueryKeys = {
    all: ["orders"] as const,
    list: ["orders", "list"] as const,
};

export function useOrdersList() {
    return useQuery({
        queryKey: ordersQueryKeys.list,
        queryFn: listOrders,
    });
}
