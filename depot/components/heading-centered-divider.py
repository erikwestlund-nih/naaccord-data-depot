from django_components import Component, register

from depot.components.base_component import BaseComponent


@register("heading-centered-divider")
class HeadingCenteredDividerComponent(BaseComponent):

    template = """
        <div {% html_attrs attrs class="relative" %}>
          <div class="absolute inset-0 flex items-center" aria-hidden="true">
            <div class="w-full border-t border-gray-300"></div>
          </div>
          <div class="relative flex justify-center">
            <span class="bg-white px-3 text-base font-semibold text-gray-900">{% slot "body" default /%}</span>
          </div>
        </div>
    """
