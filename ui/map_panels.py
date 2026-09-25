from dash import html

from ui.controls import upload_control, opacity_control


def create_map_panel(
    title,
    subtitle,
    upload_id,
    upload_label,
    opacity_id,
    map_component,
    status_id,
):
    return html.Div(
        className="map-panel",
        children=[

            html.Div(
                className="map-header",
                children=[

                    html.Div(
                        className="map-title-area",
                        children=[
                            html.Div(
                                title,
                                className="map-title",
                            ),
                            html.Div(
                                subtitle,
                                className="map-subtitle",
                            ),
                        ],
                    ),

                    upload_control(
                        upload_id,
                        upload_label,
                    ),
                ],
            ),

            html.Div(
                id=status_id,
                className="map-status",
                children="No layer loaded",
            ),

            html.Div(
                className="map-container",
                children=map_component,
            ),

            html.Div(
                className="map-footer",
                children=[
                    opacity_control(opacity_id),
                ],
            ),
        ],
    )