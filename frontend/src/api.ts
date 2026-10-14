// A small typed client for Liming's JSON API. Types come from the server's OpenAPI
// description (npm run api-types), so a change on the server shows up here as a type error.
import type { components } from "./api-types";

type Schemas = components["schemas"];
export type Plan = Schemas["PlanOut"];
export type Day = Schemas["DayOut"];
export type Item = Schemas["ItemOut"];
export type Questions = Schemas["QuestionsOut"];
export type Answers = Schemas["AnswersIn"];
export type Booking = Schemas["BookingOut"];
export type Alternative = Schemas["AlternativeOut"];
export type StayChoice = Schemas["StayChoiceOut"];
export type Catalogue = Schemas["CatalogueOut"];
export type TripSummary = Schemas["TripSummary"];
export type Me = Schemas["MeOut"];
export type Refund = Schemas["RefundOut"];

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

let csrfToken: string | null = null;
let onSignedOut: () => void = () => {};

export function setCsrf(token: string | null) {
  csrfToken = token;
}

export function whenSignedOut(handler: () => void) {
  onSignedOut = handler;
}

export async function api<T>(method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Can't reach Liming. Is the server still running?", 0);
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/me" && !path.startsWith("/api/auth/")) onSignedOut();
    throw new ApiError(data.detail ?? `Something went wrong (error ${response.status})`, response.status);
  }
  return data as T;
}
