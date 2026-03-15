"use client";

import { useEffect, useState } from "react";
import type { RateLimitStatus } from "@/lib/types";

function GaugeBar({
    label,
    used,
    max,
    unit,
    color,
}: {
    label: string;
    used: number;
    max: number;
    unit: string;
    color: string;
}) {
    const pct = max > 0 ? Math.min((used / max) * 100, 100) : 0;
    const isWarning = pct > 70;
    const isDanger = pct > 90;

    return (
        <div className="mb-3 last:mb-0">
            <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-400">{label}</span>
                <span className="text-xs mono text-slate-500">
                    {used.toLocaleString()} / {max.toLocaleString()} {unit}
                </span>
            </div>
            <div className="gauge-track">
                <div
                    className="gauge-fill transition-all duration-700 ease-out"
                    style={{
                        width: `${pct}%`,
                        background: isDanger
                            ? "linear-gradient(90deg, #ef4444, #dc2626)"
                            : isWarning
                                ? "linear-gradient(90deg, #f59e0b, #ef4444)"
                                : `linear-gradient(90deg, ${color}, ${color}cc)`,
                    }}
                />
            </div>
            <div className="flex justify-end mt-0.5">
                <span
                    className={`text-[10px] mono ${isDanger
                            ? "text-red-400"
                            : isWarning
                                ? "text-amber-400"
                                : "text-slate-600"
                        }`}
                >
                    {pct.toFixed(1)}%
                </span>
            </div>
        </div>
    );
}

export function RateLimitGauge() {
    const [status, setStatus] = useState<RateLimitStatus | null>(null);
    const [error, setError] = useState(false);

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const apiUrl =
                    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
                const res = await fetch(`${apiUrl}/api/rate-limit/status`);
                if (res.ok) {
                    setStatus(await res.json());
                    setError(false);
                }
            } catch {
                setError(true);
            }
        };

        fetchStatus();
        const interval = setInterval(fetchStatus, 5000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="glass-card p-4">
            <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
                    Rate Limits
                </h3>
                <span className={`badge ${error ? "badge-failed" : "badge-completed"}`}>
                    <span
                        className={`w-1.5 h-1.5 rounded-full ${error ? "bg-red-400" : "bg-emerald-400 animate-pulse-glow"
                            }`}
                    />
                    {error ? "Offline" : "Live"}
                </span>
            </div>

            {status ? (
                <>
                    <GaugeBar
                        label="Requests/min"
                        used={status.rpm_used}
                        max={status.rpm_max}
                        unit="RPM"
                        color="#6366f1"
                    />
                    <GaugeBar
                        label="Requests/day"
                        used={status.rpd_used}
                        max={status.rpd_max}
                        unit="RPD"
                        color="#8b5cf6"
                    />
                    <GaugeBar
                        label="Tokens/min"
                        used={status.tpm_used}
                        max={status.tpm_max}
                        unit="TPM"
                        color="#a78bfa"
                    />
                </>
            ) : (
                <div className="text-center py-4">
                    <p className="text-xs text-slate-500">
                        {error ? "Backend not reachable" : "Loading..."}
                    </p>
                </div>
            )}
        </div>
    );
}
