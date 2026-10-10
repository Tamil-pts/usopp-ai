import React from 'react';
import { Search, Play, CheckCircle2, AlertTriangle, Clock } from 'lucide-react';
import { GroupResponseData } from '../types';
import {groupOutcome} from '../utils/groupResult';

interface GroupInfo {
  groupCode: number;
  screenName: string;
  paramCount: number;
}

interface GroupSelectorBarProps {
  groups: GroupInfo[];
  selectedGroupCode: number;
  onSelectGroup: (code: number) => void;
  onTestGroup: (code: number) => void;
  groupResponses: Record<number, GroupResponseData>;
  isPollingGroup: boolean;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}

export const GroupSelectorBar: React.FC<GroupSelectorBarProps> = ({
  groups,
  selectedGroupCode,
  onSelectGroup,
  onTestGroup,
  groupResponses,
  isPollingGroup,
  searchQuery,
  onSearchChange,
}) => {
  return (
    <div className="bg-slate-900 border-b border-slate-800 p-4">
      {/* Search & Filter */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 mb-3.5">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search parameter, tag code, or group..."
            className="w-full bg-slate-800/80 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
          />
        </div>

        <div className="text-xs text-slate-400 flex items-center gap-3">
          <span>{groups.length} Groups mapped</span>
          <span className="h-3 w-px bg-slate-700" />
          <span className="flex items-center gap-1.5 text-emerald-400">
            <CheckCircle2 className="w-3.5 h-3.5" />
            {Object.values(groupResponses).filter((g) => groupOutcome(g) === 'passed').length} Passed
          </span>
        </div>
      </div>

      {/* Horizontal scrolling group code pills */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1.5 scrollbar-thin scrollbar-thumb-slate-700">
        {groups.map((grp) => {
          const isSelected = grp.groupCode === selectedGroupCode;
          const resp = groupResponses[grp.groupCode];

          return (
            <div
              key={grp.groupCode}
              className={`flex items-center rounded-lg border text-xs font-medium shrink-0 transition-all ${
                isSelected
                  ? 'bg-emerald-950/80 border-emerald-500/80 text-emerald-200 shadow-sm shadow-emerald-500/10'
                  : 'bg-slate-800/80 border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:border-slate-600'
              }`}
            >
              <button
                onClick={() => onSelectGroup(grp.groupCode)}
                className="px-3 py-2 flex items-center gap-2"
              >
                {resp ? (
                  groupOutcome(resp) === 'skipped' ? (
                    <Clock aria-label="Not requested" className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                  ) : groupOutcome(resp) === 'passed' ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  ) : (
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                  )
                ) : (
                  <Clock className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                )}

                <div className="text-left">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold">GC {grp.groupCode}</span>
                    <span className="text-[10px] opacity-70">({grp.paramCount})</span>
                  </div>
                  <div className="text-[10px] text-slate-400 truncate max-w-[120px]">
                    {grp.screenName}
                  </div>
                </div>
              </button>

              {/* Individual quick poll button */}
              <button
                onClick={() => onTestGroup(grp.groupCode)}
                disabled={isPollingGroup}
                title={`Poll Group Code ${grp.groupCode}`}
                className="px-2 py-2 border-l border-slate-700/60 hover:text-emerald-400 text-slate-400 transition-colors"
              >
                <Play className="w-3 h-3 fill-current" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};
