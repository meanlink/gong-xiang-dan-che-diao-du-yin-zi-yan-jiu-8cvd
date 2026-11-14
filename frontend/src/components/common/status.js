import {JobStatus, DeliveryStatus} from '../../constants/enums.js';
import {esc} from '../../utils/dom.js';
export const status=v=>'<span class="status '+esc(v)+'">'+esc(JobStatus[v]||v)+'</span>';
export const deliveryStatus=v=>'<span class="status '+esc(v)+'">'+esc(DeliveryStatus[v]||v)+'</span>';
