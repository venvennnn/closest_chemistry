"use client";

import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AnalysisResult } from "@/lib/api";

const tooltipStyle = { background: "#fff", border: "1px solid #f0e7e4", borderRadius: 12, fontSize: 12 };

export function UnlockRanking({ result }: { result: AnalysisResult }) {
  const data = result.standalone.map((row) => ({
    name: String(row.name || row.product_id),
    standalone: Number(row.standalone_f || 0),
    conditional: Number(row.basket_conditional_f || 0),
  }));
  return (
    <div>
      <h3 className="text-lg font-semibold tracking-tight">What each piece adds</h3>
      <p className="mb-3 text-[11px] text-muted">
        Conceptual contribution: standalone f({"{x}"}) versus basket-conditional yield. Overlapping yields are not additive.
      </p>
      <div className="no-grid h-40">
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 8 }}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="name" width={92} axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
            <Tooltip contentStyle={tooltipStyle} />
            <Bar dataKey="standalone" name="Standalone yield" fill="#ff7eb3" radius={6} barSize={10} />
            <Bar dataKey="conditional" name="Basket-conditional" fill="#9dba8c" radius={6} barSize={10} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function BudgetFrontier({ result }: { result: AnalysisResult }) {
  const data = result.frontier.map((row) => ({
    cost: Number(row.breakpoint_minor || row.cost_minor || 0) / 100,
    f: Number(row.objective_value || 0),
  }));
  return (
    <div>
      <h3 className="text-lg font-semibold tracking-tight">Options within your budget</h3>
      <p className="mb-3 text-[11px] text-muted">
        Distinct outfit options at feasible price breakpoints. Discrete steps — not a smoothed curve.
      </p>
      <div className="no-grid h-40">
        <ResponsiveContainer>
          <LineChart data={data}>
            <XAxis dataKey="cost" axisLine={false} tickLine={false} tick={{ fontSize: 11 }} label={{ value: "Budget", position: "insideBottom", offset: -2, fontSize: 10, fill: "#7a7270" }} />
            <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
            <Tooltip contentStyle={tooltipStyle} />
            <Line dataKey="f" stroke="#ff2d8b" strokeWidth={2} name="Exact f(A)" type="stepAfter" dot={{ r: 3, fill: "#ff2d8b" }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function SynergyMatrix({ result }: { result: AnalysisResult }) {
  return (
    <div>
      <h3 className="text-lg font-semibold tracking-tight">Purchase synergy</h3>
      <p className="mb-3 text-xs text-muted">
        f({"{i,j}"}) − f({"{i}"}) − f({"{j}"}). Positive complementarity versus negative overlap.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-muted">
              <th className="py-2 font-medium">Pair</th>
              <th>f i</th>
              <th>f j</th>
              <th>f ij</th>
              <th>Synergy</th>
            </tr>
          </thead>
          <tbody>
            {result.synergy.map((row) => (
              <tr key={`${row.i}-${row.j}`} className="border-t border-line" title={String(row.explanation)}>
                <td className="py-2">
                  {String(row.i_name)} + {String(row.j_name)}
                </td>
                <td>{String(row.f_i)}</td>
                <td>{String(row.f_j)}</td>
                <td>{String(row.f_ij)}</td>
                <td className={Number(row.synergy) > 0 ? "text-green" : Number(row.synergy) < 0 ? "text-coral" : ""}>
                  {String(row.synergy)}
                </td>
              </tr>
            ))}
            {!result.synergy.length && (
              <tr>
                <td className="py-4 text-muted" colSpan={5}>
                  Synergy appears after an analysis with at least two candidates.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AlgorithmCompare({ result }: { result: AnalysisResult }) {
  const data = result.comparison.map((row) => ({
    method: String(row.method).replace(/_/g, " "),
    value: Number(row.objective_value || 0),
    gap: row.percentage_gap_defined ? String(row.absolute_gap) : "undefined",
    ids: (row.product_ids as string[]) || [],
  }));
  return (
    <div>
      <h3 className="text-lg font-semibold tracking-tight">Build a better basket</h3>
      <p className="mb-3 text-xs text-muted">
        Exact search versus baselines under the same budget. Percentage gaps are undefined when the optimum is zero.
      </p>
      <div className="space-y-2">
        {data.map((row) => (
          <div key={row.method} className="flex items-center justify-between rounded-2xl bg-cream px-3 py-2 text-xs">
            <span className="capitalize">{row.method}</span>
            <span className="font-medium">{row.value} options · gap {row.gap}</span>
          </div>
        ))}
        {!data.length && <p className="text-xs text-muted">Run an analysis to compare baskets.</p>}
      </div>
    </div>
  );
}
