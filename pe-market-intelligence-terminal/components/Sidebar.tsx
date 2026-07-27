import React from 'react';
import { NavLink } from 'react-router-dom';
import { BarChart3, Target, Radio, Calculator, Settings, LogOut, Landmark, TrendingUp, Network, BookOpen, KanbanSquare, Building2 } from 'lucide-react';

const menuItems = [
  { to: '/', label: 'Market Intelligence', icon: BarChart3 },
  { to: '/sourcing', label: 'Deal Sourcing', icon: Target },
  { to: '/pipeline', label: 'Deal Pipeline', icon: KanbanSquare },
  { to: '/news', label: 'News & Signals', icon: Radio },
  { to: '/lbo', label: 'LBO Calculator', icon: Calculator },
  { to: '/comparables', label: 'Comparables', icon: Building2 },
  { to: '/buy-and-build', label: 'Buy & Build', icon: Network },
  { to: '/credit', label: 'Credit & Macro', icon: Landmark },
  { to: '/money-market', label: 'Money Market & Rates', icon: TrendingUp },
  { to: '/methodology', label: 'Méthodologie', icon: BookOpen },
];

export const Sidebar: React.FC = () => {
  return (
    <div className="w-64 h-screen fixed left-0 top-0 z-40 bg-slate-950/80 backdrop-blur-md border-r border-slate-800 flex flex-col">
      {/* Logo Area */}
      <div className="h-16 flex items-center px-6 border-b border-slate-800 bg-slate-900/50">
        <div className="w-3 h-3 bg-cyan-500 rounded-sm mr-2 animate-pulse"></div>
        <span className="font-bold text-slate-100 tracking-wider">PE<span className="text-cyan-500">TERMINAL</span></span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-6 px-3 space-y-1">
        <div className="px-3 mb-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">Main Menu</div>
        {menuItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `w-full flex items-center space-x-3 px-3 py-2.5 rounded-md transition-all duration-200 group ${
                  isActive 
                    ? 'bg-cyan-950/30 text-cyan-400 border border-cyan-900/50 shadow-[0_0_15px_rgba(6,182,212,0.1)]' 
                    : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200 border border-transparent'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={18} className={isActive ? 'text-cyan-400' : 'text-slate-500 group-hover:text-slate-300'} />
                  <span className="text-sm font-medium">{item.label}</span>
                  {isActive && <div className="ml-auto w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]"></div>}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Bottom Actions */}
      <div className="p-4 border-t border-slate-800">
        <button className="flex items-center space-x-3 w-full px-3 py-2 text-slate-500 hover:text-slate-300 transition-colors">
          <Settings size={16} />
          <span className="text-xs font-medium">Settings</span>
        </button>
        <button className="flex items-center space-x-3 w-full px-3 py-2 text-slate-500 hover:text-rose-400 transition-colors">
          <LogOut size={16} />
          <span className="text-xs font-medium">Disconnect</span>
        </button>
      </div>
    </div>
  );
};