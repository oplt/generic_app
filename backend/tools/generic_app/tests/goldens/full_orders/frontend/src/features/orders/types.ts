export type Order = {
    id: string;
    title: string;
    description: string | null;
    created_at: string;
    updated_at: string;
};

export type OrderCreate = {
    title: string;
    description?: string | null;
};

export type OrderUpdate = {
    title?: string;
    description?: string | null;
};
