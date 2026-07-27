import React from 'react';
import { Card } from './ui/Card';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid, LabelList } from 'recharts';

// Real data from Vernimmen 2025 - Invest Europe
const RAW_DATA = [
  {
    "year": 2007,
    "total_count": 1275,
    "exits": {
      "Secondary_LBO": 35,
      "Trade_Sale": 23,
      "IPO": 4,
      "Recapitalization": 19,
      "Bankruptcy": 3,
      "Other": 15
    }
  },
  {
    "year": 2010,
    "total_count": 767,
    "exits": {
      "Secondary_LBO": 39,
      "Trade_Sale": 21,
      "IPO": 5,
      "Recapitalization": 12,
      "Bankruptcy": 10,
      "Other": 13
    }
  },
  {
    "year": 2015,
    "total_count": 1042,
    "exits": {
      "Secondary_LBO": 39,
      "Trade_Sale": 29,
      "IPO": 23,
      "Recapitalization": 5,
      "Bankruptcy": 5,
      "Other": 1
    }
  },
  {
    "year": 2017,
    "total_count": 879,
    "exits": {
      "Secondary_LBO": 37,
      "Trade_Sale": 37,
      "IPO": 16,
      "Recapitalization": 6,
      "Bankruptcy": 2,
      "Other": 2
    }
  },
  {
    "year": 2018,
    "total_count": 863,
    "exits": {
      "Secondary_LBO": 46,
      "Trade_Sale": 35,
      "IPO": 10,
      "Recapitalization": 6,
      "Bankruptcy": 2,
      "Other": 1
    }
  },
  {
    "year": 2019,
    "total_count": 819,
    "exits": {
      "Secondary_LBO": 45,
      "Trade_Sale": 30,
      "IPO": 12,
      "Recapitalization": 7,
      "Bankruptcy": 4,
      "Other": 2
    }
  },
  {
    "year": 2020,
    "total_count": 619,
    "exits": {
      "Secondary_LBO": 47,
      "Trade_Sale": 23,
      "IPO": 12,
      "Recapitalization": 5,
      "Bankruptcy": 8,
      "Other": 5
    }
  },
  {
    "year": 2021,
    "total_count": 930,
    "exits": {
      "Secondary_LBO": 48,
      "Trade_Sale": 28,
      "IPO": 10,
      "Recapitalization": 10,
      "Bankruptcy": 1,
      "Other": 3
    }
  },
  {
    "year": 2022,
    "total_count": 750,
    "exits": {
      "Secondary_LBO": 55,
      "Trade_Sale": 30,
      "IPO": 2,
      "Recapitalization": 8,
      "Bankruptcy": 1,
      "Other": 4
    }
  },
  {
    "year": 2023,
    "total_count": 662,
    "exits": {
      "Secondary_LBO": 47,
      "Trade_Sale": 35,
      "IPO": 2,
      "Recapitalization": 5,
      "Bankruptcy": 7,
      "Other": 4
    }
  },
  {
    "year": 2024,
    "total_count": 789,
    "exits": {
      "Secondary_LBO": 56,
      "Trade_Sale": 21,
      "IPO": 6,
      "Recapitalization": 6,
      "Bankruptcy": 4,
      "Other": 7
    }
  }
];

// Transform data to percentages for visualization
const data = RAW_DATA.map(item => ({
  year: item.year.toString(),
  secondary: item.exits.Secondary_LBO,
  tradeSale: item.exits.Trade_Sale,
  ipo: item.exits.IPO,
  recap: item.exits.Recapitalization,
  bankruptcy: item.exits.Bankruptcy,
  other: item.exits.Other,
  total: item.total_count
}));

// Helper to render labels inside bars.
// Text color adapts based on bar background brightness.
const renderWhiteLabel = (props: any) => {
  const { x, y, width, height, value } = props;
  if (value < 5) return null; // Hide label if segment is too small to avoid clutter
  return (
    <text x={x + width / 2} y={y + height / 2} fill="#f1f5f9" textAnchor="middle" dominantBaseline="middle" fontSize={10} fontWeight="bold">
      {`${value}%`}
    </text>
  );
};

const renderDarkLabel = (props: any) => {
    const { x, y, width, height, value } = props;
    if (value < 5) return null;
    return (
      <text x={x + width / 2} y={y + height / 2} fill="#0f172a" textAnchor="middle" dominantBaseline="middle" fontSize={10} fontWeight="bold">
        {`${value}%`}
      </text>
    );
  };

const SourceBadge: React.FC = () => (
  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border text-cyan-400 border-cyan-800 bg-cyan-950/30">
    SOURCE : VERNIMMEN 2025 / INVEST EUROPE
  </span>
);

export const ExitRoutesChart: React.FC = () => {
  return (
    <Card
      title="European LBO Exit Routes Evolution"
      subtitle="Source: Vernimmen 2025 / Invest Europe"
      action={<SourceBadge />}
      className="h-[500px]"
    >
      <div className="w-full h-[430px]">
        <ResponsiveContainer width="100%" height={430}>
          <BarChart 
            data={data} 
            layout="vertical" 
            margin={{ top: 20, right: 30, left: 30, bottom: 5 }} 
            stackOffset="expand"
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
            <XAxis type="number" hide />
            <YAxis dataKey="year" type="category" stroke="#94a3b8" fontSize={11} tickLine={false} axisLine={false} width={40} />
            
            <Tooltip 
              cursor={{fill: '#1e293b', opacity: 0.4}}
              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f1f5f9', fontSize: '12px' }}
              formatter={(value: number) => `${(value * 100).toFixed(1)}%`}
              labelFormatter={(label) => `Year ${label}`}
            />
            <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} iconType="circle" />
            
            {/* Stack Order: Other -> Bankruptcy -> Recap -> IPO -> Secondary -> Trade Sale */}
            
            <Bar dataKey="other" name="Other" stackId="a" fill="#8b5cf6" radius={[4, 0, 0, 4]}>
                <LabelList dataKey="other" content={renderWhiteLabel} />
            </Bar>

            <Bar dataKey="bankruptcy" name="Bankruptcy" stackId="a" fill="#dc2626">
                <LabelList dataKey="bankruptcy" content={renderWhiteLabel} />
            </Bar>
            
            <Bar dataKey="recap" name="Recapitalization" stackId="a" fill="#fdba74">
                <LabelList dataKey="recap" content={renderDarkLabel} />
            </Bar>

            <Bar dataKey="ipo" name="IPO" stackId="a" fill="#475569">
                <LabelList dataKey="ipo" content={renderWhiteLabel} />
            </Bar>

            <Bar dataKey="secondary" name="Secondary Buyout" stackId="a" fill="#f97316">
                <LabelList dataKey="secondary" content={renderWhiteLabel} />
            </Bar>

            <Bar dataKey="tradeSale" name="Trade Sale" stackId="a" fill="#fcd34d" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="tradeSale" content={renderDarkLabel} />
            </Bar>

          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
};