import {useEffect, useState} from 'react';
import {dataModelMachineKey, type DataModel, type DataModelSummary} from '../utils/dataModelChecks';

interface ReferenceState {scope: string; models: DataModel[]; loading: boolean; error: string}
async function read(response: Response) {
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Could not read data model references.');
  return value;
}

export function useDataModelReferences(machine: string, modelId: string) {
  const scope = JSON.stringify([machine, modelId]);
  const [state, setState] = useState<ReferenceState>({scope: '', models: [], loading: true, error: ''});
  useEffect(() => {
    const request = new AbortController();
    setState({scope, models: [], loading: true, error: ''});
    const load = async () => {
      try {
        let models: DataModel[];
        let error = '';
        {
          const catalog: (DataModel | DataModelSummary)[] = await read(await fetch(
            '/api/nami/data-models?machine=' + encodeURIComponent(machine) + '&include_parameters=true&fixed_only=true',
            {signal: request.signal}));
          const selected = catalog.filter(model => dataModelMachineKey(model.machine) === dataModelMachineKey(machine));
          // Older backends return summaries even when query options are provided.
          const loaded = await Promise.allSettled(selected.map(model => 'parameters' in model ? Promise.resolve(model) :
            fetch('/api/nami/data-models/' + model.id, {signal: request.signal}).then(read) as Promise<DataModel>));
          models = loaded.flatMap(value => value.status === 'fulfilled' ? [value.value] : []);
          const failed = loaded.filter(value => value.status === 'rejected').length;
          if (failed) error = failed + ' reference model(s) could not be loaded. Reopen DataInspect to retry.';
        }
        // Reviewing one service does not hide the other fixed service models.
        // A personally imported model is included only when explicitly selected.
        if (modelId && !models.some(model => model.id === modelId)) {
          try {
            const selected: DataModel = await read(await fetch('/api/nami/data-models/' + modelId, {signal: request.signal}));
            if (!selected.fixed && dataModelMachineKey(selected.machine) === dataModelMachineKey(machine)) models.push(selected);
          } catch (reason) {
            if (request.signal.aborted) return;
            error = 'The selected additional model could not be loaded. Fixed references remain available.';
          }
        }
        if (!request.signal.aborted) setState({scope, models, loading: false, error});
      } catch (reason) {
        if (!request.signal.aborted) setState({scope, models: [], loading: false,
          error: reason instanceof Error ? reason.message : 'Could not load reference models.'});
      }
    };
    void load();
    return () => request.abort();
  }, [scope, machine, modelId]);
  return state.scope === scope ? state : {scope, models: [], loading: true, error: ''};
}
