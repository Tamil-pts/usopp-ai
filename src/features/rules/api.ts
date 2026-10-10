import {appendProjectFiles, type ProjectInput} from '../../shared/projectInput';

type RulesRequest = ProjectInput & {localProjectPath: string; rules:any};

async function responseData(response: Response) {
  const text = await response.text();
  let data:any = {};
  try { data = JSON.parse(text); } catch { /* Use the HTTP status if no JSON was returned. */ }
  if (!response.ok) throw new Error(data.detail || `Rule validation failed (HTTP ${response.status})`);
  return data;
}

export async function validateEngineeringRules(input: RulesRequest) {
  try {
    if (input.localProjectPath) {
      const response = await fetch('/api/local/rules/validate', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({project_path:input.localProjectPath,project_name:input.projectName,rules:input.rules})
      });
      return responseData(response);
    }
    const form = new FormData();
    appendProjectFiles(form, input);
    form.append('rules_json', JSON.stringify(input.rules));
    return responseData(await fetch('/api/rules/validate',{method:'POST',body:form}));
  } catch (error:any) {
    if (error instanceof TypeError && /fetch/i.test(error.message))
      throw new Error(`uSOPp could not reach its local API at ${window.location.origin}. Check the API status in the top bar; if unavailable, restart uSOPp and refresh this page.`);
    throw error;
  }
}
