export type UserRole = "ADMIN" | "WAREHOUSE_MANAGER" | "SUPPLY_CHAIN_MANAGER" | "ANALYST";

export type Permission =
  | "users:read"
  | "users:write"
  | "suppliers:read"
  | "suppliers:write"
  | "products:read"
  | "products:write"
  | "warehouses:read"
  | "warehouses:write"
  | "inventory:read"
  | "inventory:write"
  | "inventory:transactions:read"
  | "orders:read"
  | "orders:write"
  | "shipments:read"
  | "shipments:write"
  | "analytics:read"
  | "alerts:read";

export interface User {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  warehouse_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface Supplier {
  id: number;
  name: string;
  code: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Product {
  id: number;
  supplier_id: number;
  sku: string;
  name: string;
  description: string | null;
  unit: string;
  reorder_threshold: string | number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
  supplier?: Supplier;
}

export interface Warehouse {
  id: number;
  code: string;
  name: string;
  address: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface InventoryItem {
  id: number;
  product_id: number;
  warehouse_id: number;
  quantity: string | number;
  updated_at: string;
  product?: Product;
  warehouse?: Warehouse;
}

export type InventoryTransactionType = "ADJUSTMENT" | "TRANSFER_IN" | "TRANSFER_OUT" | "DISPATCH";

export interface InventoryTransaction {
  id: number;
  product_id: number;
  warehouse_id: number;
  delta: string | number;
  type: InventoryTransactionType;
  reason: string | null;
  reference_id: number | null;
  created_by: number;
  created_at: string;
  product?: Product;
  warehouse?: Warehouse;
}

export type OrderStatus = "PLACED" | "CONFIRMED" | "FULFILLED" | "CANCELLED";

export interface OrderItem {
  id?: number;
  order_id?: number;
  product_id: number;
  quantity: number | string;
  product?: Product;
}

export interface Order {
  id: number;
  order_number: string;
  status: OrderStatus;
  items: OrderItem[];
  created_by: number;
  created_at: string;
  updated_at: string;
  shipments?: Shipment[];
}

export type ShipmentStatus = "PACKED" | "IN_TRANSIT" | "DELIVERED";

export interface Shipment {
  id: number;
  shipment_number: string;
  order_id: number;
  status: ShipmentStatus;
  expected_delivery_at: string | null;
  actual_delivery_at: string | null;
  is_delayed: boolean;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface ShipmentStatusHistory {
  id: number;
  shipment_id: number;
  status: ShipmentStatus;
  changed_at: string;
  changed_by: number;
}

export type AlertType = "LOW_STOCK" | "SHIPMENT_OVERDUE";
export type AlertSeverity = "INFO" | "WARNING" | "CRITICAL";

export interface Alert {
  id: number;
  type: AlertType;
  severity: AlertSeverity;
  entity_type: string;
  entity_id: number;
  message: string;
  is_resolved: boolean;
  created_at: string;
  resolved_at: string | null;
}

export interface AnalyticsOverview {
  product_count: number;
  total_stock: number;
  low_stock_count: number;
  active_orders_count: number;
  in_transit_shipments_count: number;
  delayed_shipments_count: number;
}

export interface InventoryAnalytics {
  total_inventory: number;
  low_stock_items: number;
  by_warehouse: Array<{ warehouse_id: number; warehouse_name: string; total_quantity: number }>;
  by_product: Array<{ product_id: number; product_name: string; sku: string; total_quantity: number }>;
  movements_by_period?: Array<{ period: string; type: string; total_quantity: number }>;
}

export interface ShipmentAnalytics {
  delivered_count: number;
  delayed_count: number;
  on_time_count: number;
  avg_delivery_hours: number | null;
  avg_delay_hours: number | null;
  by_period?: Array<{ period: string; count: number; delayed: number }>;
}

export interface SupplierAnalytics {
  suppliers: Array<{
    supplier_id: number;
    supplier_name: string;
    supplier_code: string;
    total_orders?: number;
    total_products?: number;
    performance_score?: number | null;
  }>;
}

export interface BottleneckAnalytics {
  stages: Array<{
    stage: string;
    avg_hours: number | null;
    p50_hours: number | null;
    p90_hours: number | null;
    count: number;
  }>;
}

export interface PaginationMeta {
  page: number;
  limit: number;
  total: number;
  pages: number;
}

export interface ApiResponse<T = any> {
  success: boolean;
  data: T;
  message?: string;
}

export interface ApiPagedResponse<T = any> {
  success: boolean;
  data: T[];
  meta: PaginationMeta;
  message?: string;
}

export interface ApiError {
  code: string;
  message: string;
  details?: any;
}

export interface ApiErrorResponse {
  success: false;
  error: ApiError;
}

