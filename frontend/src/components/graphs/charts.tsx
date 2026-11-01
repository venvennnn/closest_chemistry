"use client";

import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AnalysisResult } from "@/lib/api";

const tooltipStyle = { background: "#fff", border: "1px solid #eee", borderRadius: 12 };

export function UnlockRanking({ result }: { result: AnalysisResult }) {
  const data = result.standalone.map((row) => ({
    name: String(row.name || row.product_id),
    standalone: Number(row.standalone_f || 0),
    conditional: Number(row.basket_conditional_f || 0),
    price: Number(row.price_minor || 0) / 100,
  }));
  return (
    <div className="bg-white">
      <h3 className="text-sm font-semibold">Outfit unlock ranking</h3>
      <p className="mb-3 text-xs text-muted">
        Standalone f({"{x}"}) versus basket-conditional contribution. Overlapping yields are not additive.
      </p>
      <div className="no-grid h-56">
        <ResponsiveContainer>
          <BarChart data={data}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
            <Tooltip contentStyle={tooltipStyle} />
            <Bar dataKey="standalone" name="Standalone yield" fill="#245bff" radius={6} />
            <Bar dataKey="conditional" name="Basket-conditional" fill="#1fa97a" radius={6} />
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
    items: (row.product_ids as string[] | undefined)?.length || 0,
  }));
  return (
    <div className="bg-white">
      <h3 className="text-sm font-semibold">Budget frontier</h3>
      <p className="mb-3 text-xs text-muted">
        Exact best f(A) at feasible price breakpoints. Discrete step values — not a smoothed curve.
      </p>
      <div className="no-grid h-56">
        <ResponsiveContainer>
          <LineChart data={data}>
            <XAxis dataKey="cost" axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
            <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
            <Tooltip contentStyle={tooltipStyle} />
            <Line dataKey="f" stroke="#ff6b4a" strokeWidth={2} name="Exact f(A)" type="stepAfter" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function SynergyMatrix({ result }: { result: AnalysisResult }) {
  return (
    <div className="bg-white">
      <h3 className="text-sm font-semibold">Purchase synergy matrix</h3>
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
              <tr key={`${row.i}-${row.j}`} className="border-t border-[#f6f6f6]" title={String(row.explanation)}>
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
    method: String(row.method),
    value: Number(row.objective_value || 0),
    gap: row.percentage_gap_defined ? Number(row.absolute_gap || 0) : "n/a",
  }));
  return (
    <div className="bg-white">
      <h3 className="text-sm font-semibold">Algorithm comparison</h3>
      <p className="mb-3 text-xs text-muted">
        Exact search versus baselines under the same budget. Percentage gaps are undefined when the optimum is zero.
        Superiority here is not proof of usefulness.
      </p>
      <div className="no-grid h-56">
        <ResponsiveContainer>
          <BarChart data={data}>
            <XAxis dataKey="method" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis allowDecimals={false} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={tooltipStyle} />
            <Bar dataKey="value" fill="#245bff" radius={6} name="Objective f(A)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
