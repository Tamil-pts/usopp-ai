import {useRef, type UIEvent} from 'react';

/** Keep paired panes at the same relative position, including different screen sizes. */
export function useLinkedScroll<T extends HTMLElement = HTMLDivElement>() {
  const base = useRef<T>(null);
  const developed = useRef<T>(null);
  const refs = [base, developed] as const;
  const expected = useRef<Array<{top:number;left:number}|null>>([null,null]);
  const onScroll = (index:number) => (event:UIEvent<T>) => {
    const source=event.currentTarget;
    const pending=expected.current[index];
    expected.current[index]=null;
    if(pending&&Math.abs(source.scrollTop-pending.top)<1&&Math.abs(source.scrollLeft-pending.left)<1)return;
    const peerIndex=1-index, peer=refs[peerIndex].current;
    if(!peer)return;
    const map=(position:number,sourceRange:number,targetRange:number)=>sourceRange>0?position/sourceRange*Math.max(0,targetRange):0;
    peer.scrollTop=map(source.scrollTop,source.scrollHeight-source.clientHeight,peer.scrollHeight-peer.clientHeight);
    peer.scrollLeft=map(source.scrollLeft,source.scrollWidth-source.clientWidth,peer.scrollWidth-peer.clientWidth);
    expected.current[peerIndex]={top:peer.scrollTop,left:peer.scrollLeft};
  };
  return {refs,onScroll};
}
