import React from 'react';
import { Card } from './ui/Card';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from 'recharts';

// Source: Bain PE Report 2025 / Preqin estimates
const data = [
  { year: '2019', deployed: 980, dryPowder: 1450 },
  { year: '2020', deployed: 860, dryPowder: 1750 },
  { year: '2021', deployed: 1350, dryPowder: 2050 },
  { year: '2022', deployed: 1020, dryPowder: 2750 },
  { year: '2023', deployed: 740, dryPowder: 3200 },
  { year: '2024', deployed: 850, dryPowder: 3600 },
  { year: '2025E', deployed: 480, dryPowder: 3850 },
];

const SourceBadge: React.FC = () => (
  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border text-cyan-400 border-cyan-800 bg-cyan-950/30">
    SOURCE : BAIN PE REPORT 2025 / PREQIN
  </span>
);

export const DryPowderChart: React.FC = () => {
  return (
    <Card
      title="Global Dry Powder"
      subtitle="Reserves ($B) vs. Deployed Capital — Source: Bain PE Report 2025 / Preqin estimates"
      action={<SourceBadge />}
      className="h-[380px]"
    >
      <div className="w-full h-[310px]">
        <ResponsiveContainer width="100%" height={310}>
          <BarChart data={data} margin={{ top: 20, right: 30, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="year" stroke="#94a3b8" fontSize={10} tickLine={false} axisLine={false} />
            <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value/1000}T`} />
            <Tooltip 
              cursor={{fill: '#1e293b', opacity: 0.4}}
              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f1f5f9', fontSize: '12px' }}
              itemStyle={{ paddingBottom: '4px' }}
            />
            <Legend wrapperStyle={{ fontSize: '10px', paddingTop: '10px' }} />
            <Bar dataKey="deployed" name="Deployed Capital" stackId="a" fill="#334155" radius={[0, 0, 0, 0]} />
            <Bar dataKey="dryPowder" name="Dry Powder" stackId="a" fill="#06b6d4" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
};