from unittest.mock import MagicMock

from svs_to_ometiff_gui.models import ConversionJob
from svs_to_ometiff_gui.services import ConversionService, _run_single_conversion_worker


def test_start_conversion_submits_worker_with_expected_args() -> None:
    service = ConversionService()

    executor = MagicMock()
    m_queue = object()
    request_id = "req-123"

    service._executor = executor
    service._m_queue = m_queue
    service._ensure_executor = MagicMock()
    service.create_job = MagicMock(return_value=request_id)

    job = ConversionJob(input_path="/tmp/in.svs", output_path="/tmp/out.ome.tiff")

    result_request_id = service.start_conversion(job)

    assert result_request_id == request_id
    assert job.request_id == request_id

    executor.submit.assert_called_once()
    args, kwargs = executor.submit.call_args

    assert kwargs == {}
    assert args[0] is _run_single_conversion_worker
    assert args[1:] == (request_id, job.to_converter_kwargs(), m_queue)
