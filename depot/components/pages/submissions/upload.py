from django_components import register

from depot.components.form_page_component import FormPageComponent


@register("pages.submissions.upload")
class SubmissionsUploadPage(FormPageComponent):
    data = {}
    title = "Upload A Submission"

    submission_types = [
        "Patient Record",
        "Diagnosis Record",
        "Laboratory Test Result Record",
        "Medication Record",
        "Mortality Record",
        "Genetic Data",
        "Insurance Information",
        "Hospitalizations",
        "Substance Use Survey Information",
        "Procedures",
        "Discharge Diagnosis Data",
        "HIV Acquisition Risk Factor Record",
        "Census Table",
    ]

    # language=HTML
    template = """
    {% component "layout.app" title=title %}

        {% component "page_container" heading=title %}
        
        <form>
          <div class="space-y-12">
            <div class="grid grid-cols-1 gap-x-8 gap-y-10 border-b border-gray-900/10 pb-12 md:grid-cols-3">
              <div>
                <h2 class="text-base font-semibold leading-7 text-gray-900">Submission Information</h2>
                <p class="mt-1 text-sm leading-6 text-gray-600">Provide us with some information about this submission.</p>
              </div>
        
              <div class="grid max-w-2xl grid-cols-1 gap-x-6 gap-y-8 sm:grid-cols-6 md:col-span-2">
       
                <div class='col-span-full'>
                     <fieldset>
                      <legend class="text-sm font-semibold leading-6 text-gray-900">Submission Type</legend>
                      <div class="mt-6 space-y-1">
                        {% for submission_type in submission_types %}
                        <div class="flex items-center text-xs gap-x-3">
                          <input id="submission-type-{{ forloop.counter }}" name="submission_type" type="radio" class="h-4 w-4 border-gray-300 text-indigo-600 focus:ring-indigo-600">
                          <label for="submission-type-{{ forloop.counter }}" class="block text-sm font-medium leading-6 text-gray-900">{{ submission_type }}</label>
                        </div>
                        {% endfor %}
                      </div>
                    </fieldset>
                
                </div>

                <!-- Auditor Tool Confirmation Checkbox -->
                <div class="col-span-full">
                  <div class="relative flex items-start">
                    <div class="flex h-6 items-center">
                      <input id="auditor-tool-confirmation" name="auditor_tool_confirmation" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-red-600 focus:ring-red-600">
                    </div>
                    <div class="ml-3 text-sm leading-6">
                      <label for="auditor-tool-confirmation" class="font-medium text-gray-900">I have used the auditor tool to inspect my variables and corrected all errors possible.</label>
                    </div>
                  </div>
                </div>
       
                <!-- Persistent Errors Explanation -->
                <div class="col-span-full">
                  <label for="persistent-errors" class="block text-sm font-medium leading-6 text-gray-900">Explain Any Remaining Errors</label>
                  <div class="mt-2">
                    <textarea id="persistent-errors" name="persistent_errors" rows="3" class="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-red-600 sm:text-sm sm:leading-6"></textarea>
                  </div>
                  <p class="mt-3 text-sm leading-6 text-gray-600">If there are any validation errors that you cannot resolve, please provide us context as to why.</p>
                </div>
                
                <!-- Notes -->
                <div class="col-span-full">
                  <label for="about" class="block text-sm font-medium leading-6 text-gray-900">Notes</label>
                  <div class="mt-2">
                    <textarea id="about" name="about" rows="3" class="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-red-600 sm:text-sm sm:leading-6"></textarea>
                  </div>
                  <p class="mt-3 text-sm leading-6 text-gray-600">Tell us anything we might need to know about this submission.</p>
                </div>


                <div class="col-span-full">
                  <label for="cover-photo" class="block text-sm font-medium leading-6 text-gray-900">Submission File</label>
                  <div class="mt-2 flex justify-center rounded-lg border border-dashed border-gray-900/25 px-6 py-10">
                    <div class="text-center">
                      {% component "icon" icon="file-spreadsheet" family="duotone" c="h-12 w-12 text-gray-400 mx-auto" /%}
                      <div class="mt-4 flex text-sm leading-6 text-gray-600">
                        <label for="file-upload" class="relative cursor-pointer rounded-md bg-white font-semibold text-red-600 focus-within:outline-none focus-within:ring-2 focus-within:ring-red-600 focus-within:ring-offset-2 hover:text-red-500">
                          <span>Upload a file</span>
                          <input id="file-upload" name="file-upload" type="file" class="sr-only">
                        </label>
                        <p class="pl-1">or drag and drop</p>
                      </div>
                      <p class="text-xs leading-5 text-gray-600">CSV or ZIP up to 1GB</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
        
          <div class="mt-6 flex items-center justify-end gap-x-6">
            <button type="button" class="text-sm font-semibold leading-6 text-gray-900">Cancel</button>
            <button type="submit" class="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600">Submit</button>
          </div>
        </form>
        
                
        {% endcomponent %}

    {% endcomponent %}
    """
