import http from "k6/http";
import { check } from "k6";

const targetURL = __ENV.TARGET_URL || "https://130.127.133.121:8080/";
const responseType = __ENV.RESPONSE_TYPE || "text";

export const options = {
  scenarios: {
    burst_server_open_loop: {
      executor: "constant-arrival-rate",  // for the open model
      rate: Number(__ENV.RATE || 400),
      timeUnit: __ENV.TIME_UNIT || "1s",
      duration: __ENV.DURATION || "30s",
      preAllocatedVUs: Number(__ENV.PRE_ALLOCATED_VUS || 10),
      maxVUs: Number(__ENV.MAX_VUS || 1000000),
    },
  },
  thresholds: {
    checks: ["rate == 1"],
    http_req_failed: ["rate == 0"],
  },
  summaryTrendStats: [
    "avg", "min", "med", "max", "p(90)", "p(95)", "p(99)", 
    "count" 
  ],
};

export default function () {
  const res = http.get(targetURL, {
    responseType,
    tags: { name: "burst-server-root" },
  });

  check(res, {
    "status is 200": (r) => r.status === 200,
  });
}