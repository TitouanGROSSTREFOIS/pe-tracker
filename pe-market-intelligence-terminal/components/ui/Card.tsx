import React, { ReactNode } from 'react';

interface CardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}

export const Card: React.FC<CardProps> = ({ title, subtitle, children, className = '', action }) => {
  return (
    <div className={`bg-slate-900 border border-slate-700 rounded-sm flex flex-col shadow-lg overflow-hidden ${className}`}>
      <div className="px-4 py-3 border-b border-slate-700 bg-slate-800/50 flex justify-between items-center">
        <div>
          <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider">{title}</h3>
          {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
        {action && <div>{action}</div>}
      </div>
      <div className="p-4 flex-1 overflow-auto">
        {children}
      </div>
    </div>
  );
};
