import {
  ApiResponse,
  ApiPagedResponse,
  PublicTrackingInfo,
  User,
  Supplier,
  Product,
  Warehouse,
  InventoryItem,
  InventoryTransaction,
  Order,
  Shipment,
  ShipmentStatusHistory,
  Alert,
  AnalyticsOverview,
  InventoryAnalytics,
  ShipmentAnalytics,
  SupplierAnalytics,
  BottleneckAnalytics,
} from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  code: string;
  details?: any;
  status: number;

  constructor(message: string, code: string = "UNKNOWN_ERROR", status: number = 500, details?: any) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function setStoredToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("token", token);
}

export function removeStoredToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("token");
}

interface RequestOptions extends RequestInit {
  params?: Record<string, any>;
}

export async function request<T = any>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { params, headers: customHeaders, ...customOptions } = options;

  let url = `${API_BASE_URL}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        searchParams.append(key, String(value));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes("?") ? "&" : "?") + queryString;
    }
  }

  const token = getStoredToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(customHeaders || {}),
  };

  const response = await fetch(url, {
    headers,
    ...customOptions,
  });

  let data: any;
  try {
    data = await response.json();
  } catch (err) {
    data = null;
  }

  if (!response.ok) {
    const errorInfo = data?.error;
    const message =
      errorInfo?.message ||
      (typeof data?.detail === "string" ? data.detail : null) ||
      response.statusText ||
      "Request failed";
    const code = errorInfo?.code || `HTTP_${response.status}`;
    const details = errorInfo?.details || data?.detail;
    throw new ApiError(message, code, response.status, details);
  }

  return data;
}

// ------------------- AUTH -------------------
export const authApi = {
  login: async (email: string, password: string): Promise<{ access_token: string; token_type: string }> => {
    const res = await request<ApiResponse<{ access_token: string; token_type: string }>>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    return res.data;
  },
  me: async (): Promise<User> => {
    const res = await request<ApiResponse<User>>("/auth/me");
    return res.data;
  },
};

// ------------------- ANALYTICS -------------------
export const analyticsApi = {
  getOverview: async (): Promise<AnalyticsOverview> => {
    const res = await request<ApiResponse<AnalyticsOverview>>("/analytics/overview");
    return res.data;
  },
  getInventory: async (period?: "day" | "week" | "month", days?: number): Promise<InventoryAnalytics> => {
    const res = await request<ApiResponse<InventoryAnalytics>>("/analytics/inventory", {
      params: { period, days },
    });
    return res.data;
  },
  getShipments: async (period?: "day" | "week" | "month", days?: number): Promise<ShipmentAnalytics> => {
    const res = await request<ApiResponse<ShipmentAnalytics>>("/analytics/shipments", {
      params: { period, days },
    });
    return res.data;
  },
  getSuppliers: async (): Promise<SupplierAnalytics> => {
    const res = await request<ApiResponse<SupplierAnalytics>>("/analytics/suppliers");
    return res.data;
  },
  getBottlenecks: async (): Promise<BottleneckAnalytics> => {
    const res = await request<ApiResponse<BottleneckAnalytics>>("/analytics/bottlenecks");
    return res.data;
  },
};

// ------------------- INVENTORY -------------------
export const inventoryApi = {
  list: async (params?: {
    page?: number;
    limit?: number;
    product_id?: number;
    warehouse_id?: number;
    below_threshold?: boolean;
  }): Promise<ApiPagedResponse<InventoryItem>> => {
    return request<ApiPagedResponse<InventoryItem>>("/inventory", { params });
  },
  get: async (id: number): Promise<InventoryItem> => {
    const res = await request<ApiResponse<InventoryItem>>(`/inventory/${id}`);
    return res.data;
  },
  adjust: async (payload: {
    product_id: number;
    warehouse_id: number;
    delta: number | string;
    reason?: string;
  }): Promise<InventoryItem> => {
    const res = await request<ApiResponse<InventoryItem>>("/inventory/adjust", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
  transfer: async (payload: {
    product_id: number;
    from_warehouse_id: number;
    to_warehouse_id: number;
    quantity: number | string;
  }): Promise<{ from: InventoryItem; to: InventoryItem }> => {
    const res = await request<ApiResponse<{ from: InventoryItem; to: InventoryItem }>>("/inventory/transfer", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
  transactions: async (params?: {
    page?: number;
    limit?: number;
    product_id?: number;
    warehouse_id?: number;
    type?: string;
    start?: string;
    end?: string;
  }): Promise<ApiPagedResponse<InventoryTransaction>> => {
    return request<ApiPagedResponse<InventoryTransaction>>("/inventory/transactions", { params });
  },
};

// ------------------- ORDERS -------------------
export const ordersApi = {
  list: async (params?: {
    page?: number;
    limit?: number;
    status?: string;
    created_by?: number;
    start?: string;
    end?: string;
    include_shipments?: boolean;
  }): Promise<ApiPagedResponse<Order>> => {
    return request<ApiPagedResponse<Order>>("/orders", { params });
  },
  get: async (id: number, include_shipments: boolean = true): Promise<Order> => {
    const res = await request<ApiResponse<Order>>(`/orders/${id}`, {
      params: { include_shipments },
    });
    return res.data;
  },
  create: async (payload: {
    items: Array<{ product_id: number; quantity: number | string }>;
  }): Promise<Order> => {
    const res = await request<ApiResponse<Order>>("/orders", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
  confirm: async (id: number): Promise<Order> => {
    const res = await request<ApiResponse<Order>>(`/orders/${id}/confirm`, {
      method: "POST",
    });
    return res.data;
  },
  fulfill: async (id: number): Promise<Order> => {
    const res = await request<ApiResponse<Order>>(`/orders/${id}/fulfill`, {
      method: "POST",
    });
    return res.data;
  },
  cancel: async (id: number): Promise<Order> => {
    const res = await request<ApiResponse<Order>>(`/orders/${id}/cancel`, {
      method: "POST",
    });
    return res.data;
  },
};

// ------------------- SHIPMENTS -------------------
export const shipmentsApi = {
  list: async (params?: {
    page?: number;
    limit?: number;
    order_id?: number;
    status?: string;
    is_delayed?: boolean;
    start?: string;
    end?: string;
  }): Promise<ApiPagedResponse<Shipment>> => {
    return request<ApiPagedResponse<Shipment>>("/shipments", { params });
  },
  get: async (id: number): Promise<Shipment> => {
    const res = await request<ApiResponse<Shipment>>(`/shipments/${id}`);
    return res.data;
  },
  history: async (id: number): Promise<ShipmentStatusHistory[]> => {
    const res = await request<ApiResponse<ShipmentStatusHistory[]>>(`/shipments/${id}/history`);
    return res.data;
  },
  create: async (payload: {
    order_id: number;
    expected_delivery_at?: string | null;
  }): Promise<Shipment> => {
    const res = await request<ApiResponse<Shipment>>("/shipments", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
  dispatch: async (
    id: number,
    payload: { warehouse_id: number; expected_delivery_at?: string | null }
  ): Promise<Shipment> => {
    const res = await request<ApiResponse<Shipment>>(`/shipments/${id}/dispatch`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
  deliver: async (id: number): Promise<Shipment> => {
    const res = await request<ApiResponse<Shipment>>(`/shipments/${id}/deliver`, {
      method: "POST",
    });
    return res.data;
  },
};

// ------------------- PRODUCTS -------------------
export const productsApi = {
  list: async (params?: {
    page?: number;
    limit?: number;
    supplier_id?: number;
    sku?: string;
    is_active?: boolean;
  }): Promise<ApiPagedResponse<Product>> => {
    return request<ApiPagedResponse<Product>>("/products", { params });
  },
  get: async (id: number): Promise<Product> => {
    const res = await request<ApiResponse<Product>>(`/products/${id}`);
    return res.data;
  },
  create: async (payload: {
    supplier_id: number;
    sku: string;
    name: string;
    description?: string;
    unit?: string;
    reorder_threshold?: number | string;
  }): Promise<Product> => {
    const res = await request<ApiResponse<Product>>("/products", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
  update: async (
    id: number,
    payload: Partial<{
      name: string;
      description: string;
      unit: string;
      reorder_threshold: number | string;
      is_active: boolean;
    }>
  ): Promise<Product> => {
    const res = await request<ApiResponse<Product>>(`/products/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
};

// ------------------- SUPPLIERS -------------------
export const suppliersApi = {
  list: async (params?: {
    page?: number;
    limit?: number;
    name?: string;
    code?: string;
    is_active?: boolean;
  }): Promise<ApiPagedResponse<Supplier>> => {
    return request<ApiPagedResponse<Supplier>>("/suppliers", { params });
  },
  get: async (id: number): Promise<Supplier> => {
    const res = await request<ApiResponse<Supplier>>(`/suppliers/${id}`);
    return res.data;
  },
  create: async (payload: {
    name: string;
    code: string;
    contact_name?: string;
    email?: string;
    phone?: string;
    address?: string;
  }): Promise<Supplier> => {
    const res = await request<ApiResponse<Supplier>>("/suppliers", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
  update: async (
    id: number,
    payload: Partial<{
      name: string;
      contact_name: string;
      email: string;
      phone: string;
      address: string;
      is_active: boolean;
    }>
  ): Promise<Supplier> => {
    const res = await request<ApiResponse<Supplier>>(`/suppliers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
};

// ------------------- WAREHOUSES -------------------
export const warehousesApi = {
  list: async (params?: {
    page?: number;
    limit?: number;
    is_active?: boolean;
  }): Promise<ApiPagedResponse<Warehouse>> => {
    return request<ApiPagedResponse<Warehouse>>("/warehouses", { params });
  },
  get: async (id: number): Promise<Warehouse> => {
    const res = await request<ApiResponse<Warehouse>>(`/warehouses/${id}`);
    return res.data;
  },
  create: async (payload: {
    code: string;
    name: string;
    address?: string;
  }): Promise<Warehouse> => {
    const res = await request<ApiResponse<Warehouse>>("/warehouses", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
  update: async (
    id: number,
    payload: Partial<{
      name: string;
      address: string;
      is_active: boolean;
    }>
  ): Promise<Warehouse> => {
    const res = await request<ApiResponse<Warehouse>>(`/warehouses/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    return res.data;
  },
};

// ------------------- ALERTS -------------------
export const alertsApi = {
  list: async (params?: {
    page?: number;
    limit?: number;
    type?: string;
    severity?: string;
    entity_type?: string;
    entity_id?: number;
    resolved?: boolean;
  }): Promise<ApiPagedResponse<Alert>> => {
    return request<ApiPagedResponse<Alert>>("/alerts", { params });
  },
  get: async (id: number): Promise<Alert> => {
    const res = await request<ApiResponse<Alert>>(`/alerts/${id}`);
    return res.data;
  },
};

// ------------------- PUBLIC TRACKING (no authentication required) -------------------
export const trackingApi = {
  get: async (trackingNumber: string): Promise<PublicTrackingInfo> => {
    const res = await request<ApiResponse<PublicTrackingInfo>>(
      `/public/tracking/${encodeURIComponent(trackingNumber.trim())}`
    );
    return res.data;
  },
};

// ------------------- USERS -------------------
export const usersApi = {
  list: async (params?: {
    page?: number;
    limit?: number;
    email?: string;
    role?: string;
    is_active?: boolean;
  }): Promise<ApiPagedResponse<User>> => {
    return request<ApiPagedResponse<User>>("/users", { params });
  },
};

