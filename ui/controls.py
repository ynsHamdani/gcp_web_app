from dash import html, dcc


def upload_control(
    component_id: str,
    label: str,
):
    return dcc.Upload(
        id=component_id,
        children=html.Button(
            label,
            className="upload-button",
        ),
        multiple=False,
        accept=".tif,.tiff",
    )


def opacity_control(
    component_id: str,
):
    return html.Div(
        className="opacity-control",
        children=[
            html.Span(
                "Opacity",
                className="opacity-label",
            ),
            dcc.Slider(
                id=component_id,
                min=0,
                max=100,
                step=5,
                value=100,
                marks=None,
                tooltip={
                    "placement": "top",
                    "always_visible": False,
                },
            ),
        ],
    )


def bottom_controls():
    return html.Div(
        className="bottom-controls",
        children=[

            html.Div(
                className="gcp-status-block",
                children=[
                    html.Div(
                        "GCP 001",
                        className="gcp-title",
                    ),
                    html.Div(
                        "Select corresponding features in the two maps",
                        id="gcp-status",
                        className="gcp-status",
                    ),
                ],
            ),

            html.Div(
                className="gcp-buttons",
                children=[
                    html.Button(
                        "Add GCP",
                        id="add-gcp-button",
                        className="primary-button",
                    ),

                    html.Button(
                        "Save GCP",
                        id="save-gcp-button",
                        disabled=True,
                        className="secondary-button",
                    ),

                    html.Button(
                        "Next",
                        id="next-button",
                        className="secondary-button",
                    ),
                ],
            ),
        ],
    )