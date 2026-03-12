import { log } from "@/lib/logger";
import {
  resilientFetch as _resilientFetch,
  isNetworkError,
  ApiError,
  type FetchOptions,
} from "@centaur/api-client";

const API_URL = process.env.CENTAUR_API_URL || "http://api:8000";
const API_KEY = process.env.SLACKBOT_API_KEY || "";

/**
 * Service-bound resilientFetch — injects SLACKBOT_API_KEY and structured logger.
 */
export async function resilientFetch(
  url: string,
  opts: FetchOptions = {},
): Promise<Response> {
  return _resilientFetch(url, opts, API_KEY, log);
}

export { API_URL, isNetworkError, ApiError };
