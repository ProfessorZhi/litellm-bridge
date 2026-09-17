(globalThis.TURBOPACK||(globalThis.TURBOPACK=[])).push(["object"==typeof document?document.currentScript:void 0,164668,e=>{"use strict";var t=e.i(717521);e.s(["LoaderCircle",()=>t.default])},62478,e=>{"use strict";var t=e.i(602869);let r=async e=>{if(!e)return null;try{return await (0,t.getProxyUISettings)(e)}catch(e){return console.error("Error fetching proxy settings:",e),null}};e.s(["fetchProxySettings",0,r])},592392,e=>{"use strict";var t=e.i(62478),r=e.i(266027);let i=(0,e.i(243652).createQueryKeys)("proxySettings"),a={PROXY_BASE_URL:"",PROXY_LOGOUT_URL:"",LITELLM_UI_API_DOC_BASE_URL:null};e.s(["default",0,function(e){let{data:n}=(0,r.useQuery)({queryKey:[...i.all,e],queryFn:()=>(0,t.fetchProxySettings)(e),enabled:!!e});return n??a}])},283713,e=>{"use strict";var t=e.i(271645),r=e.i(602869),i=e.i(612256);let a="litellm_selected_worker_id";e.s(["useWorker",0,()=>{let{data:e}=(0,i.useUIConfig)(),n=e?.is_control_plane??!1,o=e?.workers??[],[s,l]=(0,t.useState)(()=>localStorage.getItem(a));(0,t.useEffect)(()=>{if(!s||0===o.length)return;let e=o.find(e=>e.worker_id===s);e&&(0,r.switchToWorkerUrl)(e.url)},[s,o]);let d=o.find(e=>e.worker_id===s)??null,p=(0,t.useCallback)(e=>{let t=o.find(t=>t.worker_id===e);t&&(l(e),localStorage.setItem(a,e),(0,r.switchToWorkerUrl)(t.url))},[o]);return{isControlPlane:n,workers:o,selectedWorkerId:s,selectedWorker:d,selectWorker:p,disconnectFromWorker:(0,t.useCallback)(()=>{l(null),localStorage.removeItem(a),(0,r.switchToWorkerUrl)(null)},[])}}])},195057,(e,t,r)=>{"use strict";Object.defineProperty(r,"__esModule",{value:!0});var i={formatUrl:function(){return s},formatWithValidation:function(){return d},urlObjectKeys:function(){return l}};for(var a in i)Object.defineProperty(r,a,{enumerable:!0,get:i[a]});let n=e.r(190809)._(e.r(998183)),o=/https?|ftp|gopher|file/;function s(e){let{auth:t,hostname:r}=e,i=e.protocol||"",a=e.pathname||"",s=e.hash||"",l=e.query||"",d=!1;t=t?encodeURIComponent(t).replace(/%3A/i,":")+"@":"",e.host?d=t+e.host:r&&(d=t+(~r.indexOf(":")?`[${r}]`:r),e.port&&(d+=":"+e.port)),l&&"object"==typeof l&&(l=String(n.urlQueryToSearchParams(l)));let p=e.search||l&&`?${l}`||"";return i&&!i.endsWith(":")&&(i+=":"),e.slashes||(!i||o.test(i))&&!1!==d?(d="//"+(d||""),a&&"/"!==a[0]&&(a="/"+a)):d||(d=""),s&&"#"!==s[0]&&(s="#"+s),p&&"?"!==p[0]&&(p="?"+p),a=a.replace(/[?#]/g,encodeURIComponent),p=p.replace("#","%23"),`${i}${d}${a}${p}${s}`}let l=["auth","hash","host","hostname","href","path","pathname","port","protocol","query","search","slashes"];function d(e){return s(e)}},818581,(e,t,r)=>{"use strict";Object.defineProperty(r,"__esModule",{value:!0}),Object.defineProperty(r,"useMergedRef",{enumerable:!0,get:function(){return a}});let i=e.r(271645);function a(e,t){let r=(0,i.useRef)(null),a=(0,i.useRef)(null);return(0,i.useCallback)(i=>{if(null===i){let e=r.current;e&&(r.current=null,e());let t=a.current;t&&(a.current=null,t())}else e&&(r.current=n(e,i)),t&&(a.current=n(t,i))},[e,t])}function n(e,t){if("function"!=typeof e)return e.current=t,()=>{e.current=null};{let r=e(t);return"function"==typeof r?r:()=>e(null)}}("function"==typeof r.default||"object"==typeof r.default&&null!==r.default)&&void 0===r.default.__esModule&&(Object.defineProperty(r.default,"__esModule",{value:!0}),Object.assign(r.default,r),t.exports=r.default)},573668,(e,t,r)=>{"use strict";Object.defineProperty(r,"__esModule",{value:!0}),Object.defineProperty(r,"isLocalURL",{enumerable:!0,get:function(){return n}});let i=e.r(718967),a=e.r(652817);function n(e){if(!(0,i.isAbsoluteUrl)(e))return!0;try{let t=(0,i.getLocationOrigin)(),r=new URL(e,t);return r.origin===t&&(0,a.hasBasePath)(r.pathname)}catch(e){return!1}}},284508,(e,t,r)=>{"use strict";Object.defineProperty(r,"__esModule",{value:!0}),Object.defineProperty(r,"errorOnce",{enumerable:!0,get:function(){return i}});let i=e=>{}},522016,(e,t,r)=>{"use strict";Object.defineProperty(r,"__esModule",{value:!0});var i={default:function(){return _},useLinkStatus:function(){return b}};for(var a in i)Object.defineProperty(r,a,{enumerable:!0,get:i[a]});let n=e.r(190809),o=e.r(843476),s=n._(e.r(271645)),l=e.r(195057),d=e.r(8372),p=e.r(818581),u=e.r(718967),c=e.r(405550);e.r(233525);let m=e.r(388540),g=e.r(91949),f=e.r(573668),h=e.r(509396);function _(t){var r,i;let a,n,_,[b,x]=(0,s.useOptimistic)(g.IDLE_LINK_STATUS),v=(0,s.useRef)(null),{href:w,as:S,children:j,prefetch:k=null,passHref:E,replace:C,shallow:I,scroll:L,onClick:A,onMouseEnter:O,onTouchStart:$,legacyBehavior:T=!1,onNavigate:R,transitionTypes:P,ref:z,unstable_dynamicOnHover:N,...M}=t;a=j,T&&("string"==typeof a||"number"==typeof a)&&(a=(0,o.jsx)("a",{children:a}));let B=s.default.useContext(d.AppRouterContext),D=!1!==k,U=!1!==k?null===(i=k)||"auto"===i?h.FetchStrategy.PPR:h.FetchStrategy.Full:h.FetchStrategy.PPR,H="string"==typeof(r=S||w)?r:(0,l.formatUrl)(r);if(T){if(a?.$$typeof===Symbol.for("react.lazy"))throw Object.defineProperty(Error("`<Link legacyBehavior>` received a direct child that is either a Server Component, or JSX that was loaded with React.lazy(). This is not supported. Either remove legacyBehavior, or make the direct child a Client Component that renders the Link's `<a>` tag."),"__NEXT_ERROR_CODE",{value:"E863",enumerable:!1,configurable:!0});n=s.default.Children.only(a)}let G=T?n&&"object"==typeof n&&n.ref:z,F=s.default.useCallback(e=>(null!==B&&(v.current=(0,g.mountLinkInstance)(e,H,B,U,D,x)),()=>{v.current&&((0,g.unmountLinkForCurrentNavigation)(v.current),v.current=null),(0,g.unmountPrefetchableInstance)(e)}),[D,H,B,U,x]),W={ref:(0,p.useMergedRef)(F,G),onClick(t){T||"function"!=typeof A||A(t),T&&n.props&&"function"==typeof n.props.onClick&&n.props.onClick(t),!B||t.defaultPrevented||function(t,r,i,a,n,o,l){if("u">typeof window){let d,{nodeName:p}=t.currentTarget;if("A"===p.toUpperCase()&&((d=t.currentTarget.getAttribute("target"))&&"_self"!==d||t.metaKey||t.ctrlKey||t.shiftKey||t.altKey||t.nativeEvent&&2===t.nativeEvent.which)||t.currentTarget.hasAttribute("download"))return;if(!(0,f.isLocalURL)(r)){a&&(t.preventDefault(),location.replace(r));return}if(t.preventDefault(),o){let e=!1;if(o({preventDefault:()=>{e=!0}}),e)return}let{dispatchNavigateAction:u}=e.r(699781);s.default.startTransition(()=>{u(r,a?"replace":"push",!1===n?m.ScrollBehavior.NoScroll:m.ScrollBehavior.Default,i.current,l)})}}(t,H,v,C,L,R,P)},onMouseEnter(e){T||"function"!=typeof O||O(e),T&&n.props&&"function"==typeof n.props.onMouseEnter&&n.props.onMouseEnter(e),B&&D&&(0,g.onNavigationIntent)(e.currentTarget,!0===N)},onTouchStart:function(e){T||"function"!=typeof $||$(e),T&&n.props&&"function"==typeof n.props.onTouchStart&&n.props.onTouchStart(e),B&&D&&(0,g.onNavigationIntent)(e.currentTarget,!0===N)}};return(0,u.isAbsoluteUrl)(H)?W.href=H:T&&!E&&("a"!==n.type||"href"in n.props)||(W.href=(0,c.addBasePath)(H)),_=T?s.default.cloneElement(n,W):(0,o.jsx)("a",{...M,...W,children:a}),(0,o.jsx)(y.Provider,{value:b,children:_})}e.r(284508);let y=(0,s.createContext)(g.IDLE_LINK_STATUS),b=()=>(0,s.useContext)(y);("function"==typeof r.default||"object"==typeof r.default&&null!==r.default)&&void 0===r.default.__esModule&&(Object.defineProperty(r.default,"__esModule",{value:!0}),Object.assign(r.default,r),t.exports=r.default)},373264,e=>{"use strict";let t=(0,e.i(475254).default)("layout-grid",[["rect",{width:"7",height:"7",x:"3",y:"3",rx:"1",key:"1g98yp"}],["rect",{width:"7",height:"7",x:"14",y:"3",rx:"1",key:"6d4xhi"}],["rect",{width:"7",height:"7",x:"14",y:"14",rx:"1",key:"nxv5o0"}],["rect",{width:"7",height:"7",x:"3",y:"14",rx:"1",key:"1bb6yr"}]]);e.s(["LayoutGrid",0,t],373264)},275144,e=>{"use strict";var t=e.i(843476),r=e.i(271645),i=e.i(602869);let a=(0,r.createContext)(void 0);e.s(["ThemeProvider",0,({children:e,accessToken:n})=>{let[o,s]=(0,r.useState)(null),[l,d]=(0,r.useState)(null),[p,u]=(0,r.useState)(null);return(0,r.useEffect)(()=>{(async()=>{try{let e=(0,i.getProxyBaseUrl)(),t=e?`${e}/get/ui_theme_settings`:"/get/ui_theme_settings",r=await fetch(t,{method:"GET",headers:{"Content-Type":"application/json"}});if(r.ok){let e=await r.json();e.values?.logo_url&&s(e.values.logo_url),e.values?.logo_url_dark&&d(e.values.logo_url_dark),e.values?.favicon_url&&u(e.values.favicon_url)}}catch(e){console.warn("Failed to load theme settings from backend:",e)}})()},[]),(0,r.useEffect)(()=>{if(p){let e=document.querySelectorAll("link[rel*='icon']");if(e.length>0)e.forEach(e=>{e.href=p});else{let e=document.createElement("link");e.rel="icon",e.href=p,document.head.appendChild(e)}}},[p]),(0,t.jsx)(a.Provider,{value:{logoUrl:o,setLogoUrl:s,logoUrlDark:l,setLogoUrlDark:d,faviconUrl:p,setFaviconUrl:u},children:e})},"useTheme",0,()=>{let e=(0,r.useContext)(a);if(!e)throw Error("useTheme must be used within a ThemeProvider");return e}])},243553,e=>{"use strict";let t=(0,e.i(475254).default)("crown",[["path",{d:"M11.562 3.266a.5.5 0 0 1 .876 0L15.39 8.87a1 1 0 0 0 1.516.294L21.183 5.5a.5.5 0 0 1 .798.519l-2.834 10.246a1 1 0 0 1-.956.734H5.81a1 1 0 0 1-.957-.734L2.02 6.02a.5.5 0 0 1 .798-.519l4.276 3.664a1 1 0 0 0 1.516-.294z",key:"1vdc57"}],["path",{d:"M5 21h14",key:"11awu3"}]]);e.s(["Crown",0,t],243553)},115571,e=>{"use strict";let t="local-storage-change";e.s(["LOCAL_STORAGE_EVENT",0,t,"emitLocalStorageChange",0,function(e){window.dispatchEvent(new CustomEvent(t,{detail:{key:e}}))},"getLocalStorageItem",0,function(e){try{return window.localStorage.getItem(e)}catch(t){return console.warn(`Error reading localStorage key "${e}":`,t),null}},"removeLocalStorageItem",0,function(e){try{window.localStorage.removeItem(e)}catch(t){console.warn(`Error removing localStorage key "${e}":`,t)}},"setLocalStorageItem",0,function(e,t){try{window.localStorage.setItem(e,t)}catch(t){console.warn(`Error setting localStorage key "${e}":`,t)}}])},953651,e=>{"use strict";let t=(0,e.i(475254).default)("server",[["rect",{width:"20",height:"8",x:"2",y:"2",rx:"2",ry:"2",key:"ngkwjq"}],["rect",{width:"20",height:"8",x:"2",y:"14",rx:"2",ry:"2",key:"iecqi9"}],["line",{x1:"6",x2:"6.01",y1:"6",y2:"6",key:"16zg32"}],["line",{x1:"6",x2:"6.01",y1:"18",y2:"18",key:"nzw8ys"}]]);e.s(["default",0,t])},618393,e=>{"use strict";var t=e.i(953651);e.s(["Server",()=>t.default])},143488,e=>{"use strict";var t=e.i(266027),r=e.i(602869);let i=(0,e.i(243652).createQueryKeys)("healthReadinessDetails"),a=async e=>{let t=(0,r.getProxyBaseUrl)(),i=await fetch(`${t}/health/readiness/details`,{method:"GET",headers:{[(0,r.getGlobalLitellmHeaderName)()]:`Bearer ${e}`,"Content-Type":"application/json"}});if(!i.ok)throw Error(`Failed to fetch health readiness details: ${i.statusText}`);return i.json()};e.s(["useHealthReadinessDetails",0,e=>(0,t.useQuery)({queryKey:i.detail("readiness"),queryFn:()=>a(e),enabled:!!e,staleTime:3e5,retry:!1})])},912089,636772,e=>{"use strict";var t=e.i(115571),r=e.i(271645);function i(e){let r=t=>{"disableBouncingIcon"===t.key&&e()},i=t=>{let{key:r}=t.detail;"disableBouncingIcon"===r&&e()};return window.addEventListener("storage",r),window.addEventListener(t.LOCAL_STORAGE_EVENT,i),()=>{window.removeEventListener("storage",r),window.removeEventListener(t.LOCAL_STORAGE_EVENT,i)}}function a(){return"true"===(0,t.getLocalStorageItem)("disableBouncingIcon")}function n(e){let r=t=>{"disableShowPrompts"===t.key&&e()},i=t=>{let{key:r}=t.detail;"disableShowPrompts"===r&&e()};return window.addEventListener("storage",r),window.addEventListener(t.LOCAL_STORAGE_EVENT,i),()=>{window.removeEventListener("storage",r),window.removeEventListener(t.LOCAL_STORAGE_EVENT,i)}}function o(){return"true"===(0,t.getLocalStorageItem)("disableShowPrompts")}e.s(["useDisableBouncingIcon",0,function(){return(0,r.useSyncExternalStore)(i,a)}],912089),e.s(["useDisableShowPrompts",0,function(){return(0,r.useSyncExternalStore)(n,o)}],636772)},972518,799647,731565,e=>{"use strict";var t=e.i(475254);let r=(0,t.default)("panel-left-close",[["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2",key:"afitv7"}],["path",{d:"M9 3v18",key:"fh3hqa"}],["path",{d:"m16 15-3-3 3-3",key:"14y99z"}]]);e.s(["PanelLeftClose",0,r],972518);let i=(0,t.default)("panel-left-open",[["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2",key:"afitv7"}],["path",{d:"M9 3v18",key:"fh3hqa"}],["path",{d:"m14 9 3 3-3 3",key:"8010ee"}]]);e.s(["PanelLeftOpen",0,i],799647);var a=e.i(115571),n=e.i(271645);function o(e){let t=t=>{"disableBlogPosts"===t.key&&e()},r=t=>{let{key:r}=t.detail;"disableBlogPosts"===r&&e()};return window.addEventListener("storage",t),window.addEventListener(a.LOCAL_STORAGE_EVENT,r),()=>{window.removeEventListener("storage",t),window.removeEventListener(a.LOCAL_STORAGE_EVENT,r)}}function s(){return"true"===(0,a.getLocalStorageItem)("disableBlogPosts")}e.s(["useDisableBlogPosts",0,function(){return(0,n.useSyncExternalStore)(o,s)}],731565)},245423,e=>{"use strict";let t=(0,e.i(475254).default)("bell",[["path",{d:"M10.268 21a2 2 0 0 0 3.464 0",key:"vwvbt9"}],["path",{d:"M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326",key:"11g9vi"}]]);e.s(["Bell",0,t],245423)},222038,e=>{"use strict";e.s(["navAccountDisplayName",0,function(e,t){let r=e?.trim();if(r)return r;let i=t?.trim();return!i||/^default[_\s-]?user[_\s-]?id$/i.test(i)?"Account":i}])},292270,263488,e=>{"use strict";var t=e.i(475254);let r=(0,t.default)("log-out",[["path",{d:"m16 17 5-5-5-5",key:"1bji2h"}],["path",{d:"M21 12H9",key:"dn1m92"}],["path",{d:"M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4",key:"1uf3rs"}]]);e.s(["LogOut",0,r],292270);let i=(0,t.default)("mail",[["path",{d:"m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7",key:"132q7q"}],["rect",{x:"2",y:"4",width:"20",height:"16",rx:"2",key:"izxlao"}]]);e.s(["Mail",0,i],263488)},799676,e=>{"use strict";var t=e.i(843476);e.s([],704824),e.i(704824),e.i(247167);var r=e.i(271645),i=e.i(552245),a=e.i(733332);let n=r.createContext(void 0);function o(){let e=r.useContext(n);if(void 0===e)throw Error((0,a.default)(13));return e}let s={imageLoadingStatus:()=>null},l=r.forwardRef(function(e,a){let{className:o,render:l,style:d,...p}=e,[u,c]=r.useState("idle"),m=r.useMemo(()=>({imageLoadingStatus:u,setImageLoadingStatus:c}),[u,c]),g=(0,i.useRenderElement)("span",e,{state:{imageLoadingStatus:u},ref:a,props:p,stateAttributesMapping:s});return(0,t.jsx)(n.Provider,{value:m,children:g})});var d=e.i(667865),p=e.i(146376),u=e.i(137584),c=e.i(209407),m=e.i(223910),g=e.i(956789);let f={...s,...c.transitionStatusMapping},h=r.forwardRef(function(e,t){let{className:a,render:n,onLoadingStatusChange:s,style:l,...c}=e,{setImageLoadingStatus:h}=o(),_=function(e,{referrerPolicy:t,crossOrigin:i,sizes:a,srcSet:n}){let[o,s]=r.useState("idle");return(0,p.useIsoLayoutEffect)(()=>{if(!e&&!n)return s("error"),g.NOOP;let r=!0,o=new window.Image,l=e=>()=>{r&&s(e)};return s("loading"),o.onload=l("loaded"),o.onerror=l("error"),t&&(o.referrerPolicy=t),o.crossOrigin=i??null,a&&(o.sizes=a),n&&(o.srcset=n),e&&(o.src=e),o.complete&&s(o.naturalWidth>0?"loaded":"error"),()=>{r=!1}},[e,n,a,i,t]),o}(c.src,c),y="loaded"===_,{mounted:b,transitionStatus:x,setMounted:v}=(0,m.useTransitionStatus)(y),w=r.useRef(null),S=(0,d.useStableCallback)(e=>{s?.(e),h(e)});(0,p.useIsoLayoutEffect)(()=>{"idle"!==_&&S(_)},[_,S]),(0,p.useIsoLayoutEffect)(()=>()=>h("idle"),[h]),(0,u.useOpenChangeComplete)({open:y,ref:w,onComplete(){y||v(!1)}});let j=(0,i.useRenderElement)("img",e,{state:{imageLoadingStatus:_,transitionStatus:x},ref:[t,w],props:c,stateAttributesMapping:f,enabled:b});return b?j:null});var _=e.i(439957);let y=r.forwardRef(function(e,t){let{className:a,render:n,delay:l,style:d,...p}=e,{imageLoadingStatus:u}=o(),[c,m]=r.useState(void 0===l),g=(0,_.useTimeout)();return r.useEffect(()=>(void 0!==l?g.start(l,()=>m(!0)):m(!0),g.clear),[g,l]),(0,i.useRenderElement)("span",e,{state:{imageLoadingStatus:u},ref:t,props:p,stateAttributesMapping:s,enabled:"loaded"!==u&&(void 0===l||c)})});e.s(["Fallback",0,y,"Image",0,h,"Root",0,l],514751);var b=e.i(514751),b=b,x=e.i(196631);let v=r.forwardRef(({className:e,...r},i)=>(0,t.jsx)(b.Root,{ref:i,"data-slot":"avatar",className:(0,x.cn)("relative flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full",e),...r}));v.displayName="Avatar",r.forwardRef(({className:e,...r},i)=>(0,t.jsx)(b.Image,{ref:i,"data-slot":"avatar-image",className:(0,x.cn)("size-full object-cover",e),...r})).displayName="AvatarImage";let w=r.forwardRef(({className:e,...r},i)=>(0,t.jsx)(b.Fallback,{ref:i,"data-slot":"avatar-fallback",className:(0,x.cn)("flex size-full items-center justify-center rounded-full text-xs font-medium",e),...r}));w.displayName="AvatarFallback",e.s(["Avatar",0,v,"AvatarFallback",0,w],799676)},306228,e=>{"use strict";let t=(0,e.i(475254).default)("link-2",[["path",{d:"M9 17H7A5 5 0 0 1 7 7h2",key:"8i5ue5"}],["path",{d:"M15 7h2a5 5 0 1 1 0 10h-2",key:"1b9ql8"}],["line",{x1:"8",x2:"16",y1:"12",y2:"12",key:"1jonct"}]]);e.s(["Link2",0,t],306228)},909947,865361,e=>{"use strict";var t,r,i=((t={}).AUDIO_SPEECH="audio_speech",t.AUDIO_TRANSCRIPTION="audio_transcription",t.IMAGE_GENERATION="image_generation",t.VIDEO_GENERATION="video_generation",t.CHAT="chat",t.COMPLETION="completion",t.RESPONSES="responses",t.IMAGE_EDITS="image_edit",t.ANTHROPIC_MESSAGES="anthropic_messages",t.EMBEDDING="embedding",t.REALTIME="realtime",t),a=((r={}).IMAGE="image",r.VIDEO="video",r.CHAT="chat",r.RESPONSES="responses",r.IMAGE_EDITS="image_edits",r.ANTHROPIC_MESSAGES="anthropic_messages",r.EMBEDDINGS="embeddings",r.SPEECH="speech",r.TRANSCRIPTION="transcription",r.A2A_AGENTS="a2a_agents",r.MCP="mcp",r.REALTIME="realtime",r.INTERACTIONS="interactions",r);let n={image_generation:"image",video_generation:"video",chat:"chat",completion:"chat",responses:"responses",image_edit:"image_edits",anthropic_messages:"anthropic_messages",audio_speech:"speech",audio_transcription:"transcription",embedding:"embeddings",realtime:"realtime"};e.s(["EndpointType",()=>a,"ModelMode",()=>i,"getEndpointType",0,e=>Object.values(i).includes(e)?n[e]:"chat"],865361),e.s(["generateCodeSnippet",0,e=>{let t,{apiKeySource:r,accessToken:i,apiKey:n,inputMessage:o,chatHistory:s,selectedTags:l,selectedVectorStores:d,selectedGuardrails:p,selectedPolicies:u,selectedVoice:c,endpointType:m,selectedModel:g,selectedSdk:f,proxySettings:h}=e,_="session"===r?i:n,y=window.location.origin,b=h?.LITELLM_UI_API_DOC_BASE_URL;b&&b.trim()?y=b:h?.PROXY_BASE_URL&&(y=h.PROXY_BASE_URL);let x=o||"Your prompt here",v=x.replace(/\\/g,"\\\\").replace(/"/g,'\\"').replace(/\n/g,"\\n"),w=s.filter(e=>!e.isImage).map(({role:e,content:t})=>({role:e,content:t})),S={};l.length>0&&(S.tags=l),d.length>0&&(S.vector_stores=d),p.length>0&&(S.guardrails=p),u.length>0&&(S.policies=u);let j=g||"your-model-name",k="azure"===f?`import openai

client = openai.AzureOpenAI(
	api_key="${_||"YOUR_LITELLM_API_KEY"}",
	azure_endpoint="${y}",
	api_version="2024-02-01"
)`:`import openai

client = openai.OpenAI(
	api_key="${_||"YOUR_LITELLM_API_KEY"}",
	base_url="${y}"
)`;switch(m){case a.CHAT:{let e=Object.keys(S).length>0,r="";if(e){let e=JSON.stringify({metadata:S},null,2).split("\n").map(e=>" ".repeat(4)+e).join("\n").trim();r=`,
    extra_body=${e}`}let i=w.length>0?w:[{role:"user",content:x}];t=`
import base64

# Helper function to encode images to base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# Example with text only
response = client.chat.completions.create(
    model="${j}",
    messages=${JSON.stringify(i,null,4)}${r}
)

print(response)

# Example with image or PDF (uncomment and provide file path to use)
# base64_file = encode_image("path/to/your/file.jpg")  # or .pdf
# response_with_file = client.chat.completions.create(
#     model="${j}",
#     messages=[
#         {
#             "role": "user",
#             "content": [
#                 {
#                     "type": "text",
#                     "text": "${v}"
#                 },
#                 {
#                     "type": "image_url",
#                     "image_url": {
#                         "url": f"data:image/jpeg;base64,{base64_file}"  # or data:application/pdf;base64,{base64_file}
#                     }
#                 }
#             ]
#         }
#     ]${r}
# )
# print(response_with_file)
`;break}case a.RESPONSES:{let e=Object.keys(S).length>0,r="";if(e){let e=JSON.stringify({metadata:S},null,2).split("\n").map(e=>" ".repeat(4)+e).join("\n").trim();r=`,
    extra_body=${e}`}let i=w.length>0?w:[{role:"user",content:x}];t=`
import base64

# Helper function to encode images to base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# Example with text only
response = client.responses.create(
    model="${j}",
    input=${JSON.stringify(i,null,4)}${r}
)

print(response.output_text)

# Example with image or PDF (uncomment and provide file path to use)
# base64_file = encode_image("path/to/your/file.jpg")  # or .pdf
# response_with_file = client.responses.create(
#     model="${j}",
#     input=[
#         {
#             "role": "user",
#             "content": [
#                 {"type": "input_text", "text": "${v}"},
#                 {
#                     "type": "input_image",
#                     "image_url": f"data:image/jpeg;base64,{base64_file}",  # or data:application/pdf;base64,{base64_file}
#                 },
#             ],
#         }
#     ]${r}
# )
# print(response_with_file.output_text)
`;break}case a.IMAGE:t="azure"===f?`
# NOTE: The Azure SDK does not have a direct equivalent to the multi-modal 'responses.create' method shown for OpenAI.
# This snippet uses 'client.images.generate' and will create a new image based on your prompt.
# It does not use the uploaded image, as 'client.images.generate' does not support image inputs in this context.
import os
import requests
import json
import time
from PIL import Image

result = client.images.generate(
	model="${j}",
	prompt="${o}",
	n=1
)

json_response = json.loads(result.model_dump_json())

# Set the directory for the stored image
image_dir = os.path.join(os.curdir, 'images')

# If the directory doesn't exist, create it
if not os.path.isdir(image_dir):
	os.mkdir(image_dir)

# Initialize the image path
image_filename = f"generated_image_{int(time.time())}.png"
image_path = os.path.join(image_dir, image_filename)

try:
	# Retrieve the generated image
	if json_response.get("data") && len(json_response["data"]) > 0 && json_response["data"][0].get("url"):
			image_url = json_response["data"][0]["url"]
			generated_image = requests.get(image_url).content
			with open(image_path, "wb") as image_file:
					image_file.write(generated_image)

			print(f"Image saved to {image_path}")
			# Display the image
			image = Image.open(image_path)
			image.show()
	else:
			print("Could not find image URL in response.")
			print("Full response:", json_response)
except Exception as e:
	print(f"An error occurred: {e}")
	print("Full response:", json_response)
`:`
import base64
import os
import time
import json
from PIL import Image
import requests

# Helper function to encode images to base64
def encode_image(image_path):
	with open(image_path, "rb") as image_file:
			return base64.b64encode(image_file.read()).decode('utf-8')

# Helper function to create a file (simplified for this example)
def create_file(image_path):
	# In a real implementation, this would upload the file to OpenAI
	# For this example, we'll just return a placeholder ID
	return f"file_{os.path.basename(image_path).replace('.', '_')}"

# The prompt entered by the user
prompt = "${v}"

# Encode images to base64
base64_image1 = encode_image("body-lotion.png")
base64_image2 = encode_image("soap.png")

# Create file IDs
file_id1 = create_file("body-lotion.png")
file_id2 = create_file("incense-kit.png")

response = client.responses.create(
	model="${j}",
	input=[
			{
					"role": "user",
					"content": [
							{"type": "input_text", "text": prompt},
							{
									"type": "input_image",
									"image_url": f"data:image/jpeg;base64,{base64_image1}",
							},
							{
									"type": "input_image",
									"image_url": f"data:image/jpeg;base64,{base64_image2}",
							},
							{
									"type": "input_image",
									"file_id": file_id1,
							},
							{
									"type": "input_image",
									"file_id": file_id2,
							}
					],
			}
	],
	tools=[{"type": "image_generation"}],
)

# Process the response
image_generation_calls = [
	output
	for output in response.output
	if output.type == "image_generation_call"
]

image_data = [output.result for output in image_generation_calls]

if image_data:
	image_base64 = image_data[0]
	image_filename = f"edited_image_{int(time.time())}.png"
	with open(image_filename, "wb") as f:
			f.write(base64.b64decode(image_base64))
	print(f"Image saved to {image_filename}")
else:
	# If no image is generated, there might be a text response with an explanation
	text_response = [output.text for output in response.output if hasattr(output, 'text')]
	if text_response:
			print("No image generated. Model response:")
			print("\\n".join(text_response))
	else:
			print("No image data found in response.")
	print("Full response for debugging:")
	print(response)
`;break;case a.IMAGE_EDITS:t="azure"===f?`
import base64
import os
import time
import json
from PIL import Image
import requests

# Helper function to encode images to base64
def encode_image(image_path):
	with open(image_path, "rb") as image_file:
			return base64.b64encode(image_file.read()).decode('utf-8')

# The prompt entered by the user
prompt = "${v}"

# Encode images to base64
base64_image1 = encode_image("body-lotion.png")
base64_image2 = encode_image("soap.png")

# Create file IDs
file_id1 = create_file("body-lotion.png")
file_id2 = create_file("incense-kit.png")

response = client.responses.create(
	model="${j}",
	input=[
			{
					"role": "user",
					"content": [
							{"type": "input_text", "text": prompt},
							{
									"type": "input_image",
									"image_url": f"data:image/jpeg;base64,{base64_image1}",
							},
							{
									"type": "input_image",
									"image_url": f"data:image/jpeg;base64,{base64_image2}",
							},
							{
									"type": "input_image",
									"file_id": file_id1,
							},
							{
									"type": "input_image",
									"file_id": file_id2,
							}
					],
			}
	],
	tools=[{"type": "image_generation"}],
)

# Process the response
image_generation_calls = [
	output
	for output in response.output
	if output.type == "image_generation_call"
]

image_data = [output.result for output in image_generation_calls]

if image_data:
	image_base64 = image_data[0]
	image_filename = f"edited_image_{int(time.time())}.png"
	with open(image_filename, "wb") as f:
			f.write(base64.b64decode(image_base64))
	print(f"Image saved to {image_filename}")
else:
	# If no image is generated, there might be a text response with an explanation
	text_response = [output.text for output in response.output if hasattr(output, 'text')]
	if text_response:
			print("No image generated. Model response:")
			print("\\n".join(text_response))
	else:
			print("No image data found in response.")
	print("Full response for debugging:")
	print(response)
`:`
import base64
import os
import time

# Helper function to encode images to base64
def encode_image(image_path):
	with open(image_path, "rb") as image_file:
			return base64.b64encode(image_file.read()).decode('utf-8')

# Helper function to create a file (simplified for this example)
def create_file(image_path):
	# In a real implementation, this would upload the file to OpenAI
	# For this example, we'll just return a placeholder ID
	return f"file_{os.path.basename(image_path).replace('.', '_')}"

# The prompt entered by the user
prompt = "${v}"

# Encode images to base64
base64_image1 = encode_image("body-lotion.png")
base64_image2 = encode_image("soap.png")

# Create file IDs
file_id1 = create_file("body-lotion.png")
file_id2 = create_file("incense-kit.png")

response = client.responses.create(
	model="${j}",
	input=[
			{
					"role": "user",
					"content": [
							{"type": "input_text", "text": prompt},
							{
									"type": "input_image",
									"image_url": f"data:image/jpeg;base64,{base64_image1}",
							},
							{
									"type": "input_image",
									"image_url": f"data:image/jpeg;base64,{base64_image2}",
							},
							{
									"type": "input_image",
									"file_id": file_id1,
							},
							{
									"type": "input_image",
									"file_id": file_id2,
							}
					],
			}
	],
	tools=[{"type": "image_generation"}],
)

# Process the response
image_generation_calls = [
	output
	for output in response.output
	if output.type == "image_generation_call"
]

image_data = [output.result for output in image_generation_calls]

if image_data:
	image_base64 = image_data[0]
	image_filename = f"edited_image_{int(time.time())}.png"
	with open(image_filename, "wb") as f:
			f.write(base64.b64decode(image_base64))
	print(f"Image saved to {image_filename}")
else:
	# If no image is generated, there might be a text response with an explanation
	text_response = [output.text for output in response.output if hasattr(output, 'text')]
	if text_response:
			print("No image generated. Model response:")
			print("\\n".join(text_response))
	else:
			print("No image data found in response.")
	print("Full response for debugging:")
	print(response)
`;break;case a.EMBEDDINGS:t=`
response = client.embeddings.create(
	input="${o||"Your string here"}",
	model="${j}",
	encoding_format="base64" # or "float"
)

print(response.data[0].embedding)
`;break;case a.TRANSCRIPTION:t=`
# Open the audio file
audio_file = open("path/to/your/audio/file.mp3", "rb")

# Make the transcription request
response = client.audio.transcriptions.create(
	model="${j}",
	file=audio_file${o?`,
	prompt="${o.replace(/\\/g,"\\\\").replace(/"/g,'\\"')}"`:""}
)

print(response.text)
`;break;case a.SPEECH:t=`
# Make the text-to-speech request
response = client.audio.speech.create(
	model="${j}",
	input="${o||"Your text to convert to speech here"}",
	voice="${c}"  # Options: alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer
)

# Save the audio to a file
output_filename = "output_speech.mp3"
response.stream_to_file(output_filename)
print(f"Audio saved to {output_filename}")

# Optional: Customize response format and speed
# response = client.audio.speech.create(
#     model="${j}",
#     input="${o||"Your text to convert to speech here"}",
#     voice="alloy",
#     response_format="mp3",  # Options: mp3, opus, aac, flac, wav, pcm
#     speed=1.0  # Range: 0.25 to 4.0
# )
# response.stream_to_file("output_speech.mp3")
`;break;default:t="\n# Code generation for this endpoint is not implemented yet."}return`${k}
${t}`}],909947)},652272,209261,e=>{"use strict";var t=e.i(843476),r=e.i(271645),i=e.i(871689),a=e.i(643531),n=e.i(174886),o=e.i(306228);let s=/^[a-zA-Z0-9][a-zA-Z0-9._-]*(\/[a-zA-Z0-9][a-zA-Z0-9._-]*)*$/,l=e=>e.trim().replace(/\/+$/,""),d=/\.(md|markdown|txt|json|ya?ml|toml)$/i,p=/^\d{1,3}(\.\d{1,3}){3}$/,u=/^[A-Za-z0-9-]+$/,c=/^[A-Za-z0-9._-]+$/,m=e=>e.pathname.split("/").filter(e=>""!==e),g=e=>{let t=e.split("/").filter(e=>""!==e);return t[t.length-1]??""},f=e=>e.toLowerCase().replace(/[^a-z0-9-]+/g,"-").replace(/-+/g,"-").replace(/^-+|-+$/g,""),h=e=>JSON.stringify({extraKnownMarketplaces:{litellm:{source:{source:"url",url:`${e}/claude-code/marketplace.json`}}}},null,2),_=e=>`/plugin install ${e.name}@litellm`;e.s(["buildMarketplaceSettingsSnippet",0,h,"formatInstallCommand",0,_,"getCategoryBadgeColor",0,e=>{if(!e)return"gray";let t=e.toLowerCase();if(t.includes("development")||t.includes("dev"))return"blue";if(t.includes("productivity")||t.includes("workflow"))return"green";if(t.includes("learning")||t.includes("education"))return"purple";if(t.includes("security")||t.includes("safety"))return"red";if(t.includes("data")||t.includes("analytics"))return"orange";else if(t.includes("integration")||t.includes("api"))return"yellow";return"gray"},"isValidEmail",0,e=>!e||/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e),"isValidSemanticVersion",0,e=>!e||/^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?(\+[a-zA-Z0-9.-]+)?$/.test(e),"isValidSubPath",0,e=>{let t=l(e);return""!==t&&s.test(t)},"parseKeywords",0,e=>e&&""!==e.trim()?e.split(",").map(e=>e.trim()).filter(e=>""!==e):[],"parseSkillSource",0,(e,t)=>{let r=(e=>{let t,r=e.trim();if(""===r||r.startsWith("//"))return null;let i=/^[a-z][a-z0-9+.-]*:\/\//i.test(r)?r:`https://${r}`;try{t=new URL(i)}catch{return null}return"https:"!==t.protocol||""!==t.username||""!==t.password||!t.hostname.includes(".")||t.hostname.startsWith("[")||p.test(t.hostname)?null:t})(e);if(!r)return null;if("github.com"===r.hostname.replace(/^www\./,""))return((e,t)=>{let r=m(e);if(r.length<2)return null;let i=r[0],a=r[1].replace(/\.git$/,"");if(!u.test(i)||!c.test(a))return null;let n=`${i}/${a}`,o=`https://github.com/${n}`,p={parsed:{source:"github",repo:n},label:`GitHub repo — ${n}`,suggestedName:f(a)};if(r.length>=4&&("tree"===r[2]||"blob"===r[2])){let e=r.slice(4),t=g(e.join("/")),i=d.test(t)?e.slice(0,-1):e;if(0===i.length)return p;let a=l(i.join("/"));return s.test(a)?{parsed:{source:"git-subdir",url:o,path:a},label:`GitHub subdir — ${n} @ ${a}`,suggestedName:f(g(a))}:null}if(2!==r.length)return null;let h=l(t??"");return""!==h?s.test(h)?{parsed:{source:"git-subdir",url:o,path:h},label:`GitHub subdir — ${n} @ ${h}`,suggestedName:f(g(h))}:null:p})(r,t);if(m(r).length<2)return null;let i=`${r.protocol}//${r.host}${r.pathname.replace(/\/+$/,"")}`,a=l(t??"");return""!==a?s.test(a)?{parsed:{source:"git-subdir",url:i,path:a},label:`Git subdir — ${i} @ ${a}`,suggestedName:f(g(a))}:null:{parsed:{source:"url",url:i},label:`Git repo — ${i}`,suggestedName:f(g(r.pathname).replace(/\.git$/,""))}},"validatePluginName",0,e=>!!e&&""!==e.trim()&&/^[a-z0-9-]+$/.test(e)],209261),e.s(["default",0,({skill:e,onBack:s})=>{let l,[d,p]=(0,r.useState)("overview"),[u,c]=(0,r.useState)(null),m=(e,t)=>{navigator.clipboard.writeText(e),c(t),setTimeout(()=>c(null),2e3)},g="github"===(l=e.source).source&&l.repo?`https://github.com/${l.repo}`:"git-subdir"===l.source&&l.url?l.path?`${l.url}/tree/main/${l.path}`:l.url:"url"===l.source&&l.url?l.url:null,f=_(e),y=h(window.location.origin),b=[...e.category?[{property:"Category",value:e.category}]:[],...e.domain?[{property:"Domain",value:e.domain}]:[],...e.namespace?[{property:"Namespace",value:e.namespace}]:[],...e.version?[{property:"Version",value:e.version}]:[],...e.author?.name?[{property:"Author",value:e.author.name}]:[],...e.created_at?[{property:"Added",value:new Date(e.created_at).toLocaleDateString()}]:[]];return(0,t.jsxs)("div",{style:{padding:"24px 32px 24px 0"},children:[(0,t.jsxs)("div",{onClick:s,style:{display:"inline-flex",alignItems:"center",gap:6,color:"#5f6368",cursor:"pointer",fontSize:14,marginBottom:24},children:[(0,t.jsx)(i.ArrowLeft,{className:"size-3"}),(0,t.jsx)("span",{children:"Skills"})]}),(0,t.jsxs)("div",{style:{marginBottom:8},children:[(0,t.jsx)("h1",{style:{fontSize:28,fontWeight:400,color:"#202124",margin:0,lineHeight:1.2},children:e.name}),e.description&&(0,t.jsx)("p",{style:{fontSize:14,color:"#5f6368",margin:"8px 0 0 0",lineHeight:1.6},children:e.description})]}),(0,t.jsx)("div",{style:{borderBottom:"1px solid #dadce0",marginBottom:28,marginTop:24},children:(0,t.jsx)("div",{style:{display:"flex",gap:0},children:[{key:"overview",label:"Overview"},{key:"usage",label:"How to Use"}].map(e=>(0,t.jsx)("div",{onClick:()=>p(e.key),style:{padding:"12px 20px",fontSize:14,color:d===e.key?"#1a73e8":"#5f6368",borderBottom:d===e.key?"3px solid #1a73e8":"3px solid transparent",cursor:"pointer",fontWeight:d===e.key?500:400,marginBottom:-1},children:e.label},e.key))})}),"overview"===d&&(0,t.jsxs)("div",{style:{display:"flex",gap:64},children:[(0,t.jsxs)("div",{style:{flex:1,minWidth:0},children:[(0,t.jsx)("h2",{style:{fontSize:18,fontWeight:400,color:"#202124",margin:"0 0 4px 0"},children:"Skill Details"}),(0,t.jsx)("p",{style:{fontSize:13,color:"#5f6368",margin:"0 0 16px 0"},children:"Metadata registered with this skill"}),(0,t.jsxs)("table",{style:{width:"100%",borderCollapse:"collapse",fontSize:14},children:[(0,t.jsx)("thead",{children:(0,t.jsxs)("tr",{style:{borderBottom:"1px solid #dadce0"},children:[(0,t.jsx)("th",{style:{textAlign:"left",padding:"12px 0",color:"#5f6368",fontWeight:500,width:160},children:"Property"}),(0,t.jsx)("th",{style:{textAlign:"left",padding:"12px 0",color:"#5f6368",fontWeight:500},children:e.name})]})}),(0,t.jsx)("tbody",{children:b.map((e,r)=>(0,t.jsxs)("tr",{style:{borderBottom:"1px solid #f1f3f4"},children:[(0,t.jsx)("td",{style:{padding:"12px 0",color:"#3c4043"},children:e.property}),(0,t.jsx)("td",{style:{padding:"12px 0",color:"#202124"},children:e.value})]},r))})]})]}),(0,t.jsxs)("div",{style:{width:240,flexShrink:0},children:[(0,t.jsxs)("div",{style:{marginBottom:24},children:[(0,t.jsx)("div",{style:{fontSize:12,color:"#5f6368",marginBottom:4},children:"Status"}),(0,t.jsx)("span",{style:{fontSize:12,padding:"3px 10px",borderRadius:12,backgroundColor:e.enabled?"#e6f4ea":"#f1f3f4",color:e.enabled?"#137333":"#5f6368",fontWeight:500},children:e.enabled?"Public":"Draft"})]}),g&&(0,t.jsxs)("div",{style:{marginBottom:24},children:[(0,t.jsx)("div",{style:{fontSize:12,color:"#5f6368",marginBottom:4},children:"Source"}),(0,t.jsxs)("a",{href:g,target:"_blank",rel:"noopener noreferrer",style:{fontSize:13,color:"#1a73e8",wordBreak:"break-all",display:"flex",alignItems:"center",gap:4},children:[g.replace("https://",""),(0,t.jsx)(o.Link2,{className:"size-3 shrink-0"})]})]}),e.keywords&&e.keywords.length>0&&(0,t.jsxs)("div",{style:{marginBottom:24},children:[(0,t.jsx)("div",{style:{fontSize:12,color:"#5f6368",marginBottom:8},children:"Tags"}),(0,t.jsx)("div",{style:{display:"flex",flexWrap:"wrap",gap:6},children:e.keywords.map(e=>(0,t.jsx)("span",{style:{fontSize:12,padding:"4px 12px",borderRadius:16,border:"1px solid #dadce0",color:"#3c4043",backgroundColor:"#fff"},children:e},e))})]}),(0,t.jsxs)("div",{children:[(0,t.jsx)("div",{style:{fontSize:12,color:"#5f6368",marginBottom:4},children:"Skill ID"}),(0,t.jsx)("div",{style:{fontSize:12,fontFamily:"monospace",color:"#3c4043",wordBreak:"break-all"},children:e.id})]})]})]}),"usage"===d&&(0,t.jsxs)("div",{style:{maxWidth:640},children:[(0,t.jsx)("h2",{style:{fontSize:18,fontWeight:400,color:"#202124",margin:"0 0 8px 0"},children:"Using this skill"}),(0,t.jsx)("p",{style:{fontSize:14,color:"#5f6368",margin:"0 0 24px 0",lineHeight:1.6},children:"Once your proxy is set as a marketplace, enable this skill in Claude Code with one command:"}),(0,t.jsxs)("div",{style:{border:"1px solid #dadce0",borderRadius:8,overflow:"hidden",marginBottom:24},children:[(0,t.jsxs)("div",{style:{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"10px 16px",backgroundColor:"#f8f9fa",borderBottom:"1px solid #dadce0"},children:[(0,t.jsx)("span",{style:{fontSize:13,color:"#3c4043",fontWeight:500},children:"Run in Claude Code"}),(0,t.jsxs)("button",{onClick:()=>m(f,"install"),style:{display:"flex",alignItems:"center",gap:4,fontSize:12,color:"install"===u?"#137333":"#1a73e8",background:"none",border:"none",cursor:"pointer",padding:0},children:["install"===u?(0,t.jsx)(a.Check,{className:"size-3"}):(0,t.jsx)(n.Copy,{className:"size-3"}),"install"===u?"Copied":"Copy"]})]}),(0,t.jsx)("pre",{style:{margin:0,padding:"14px 16px",fontSize:14,fontFamily:"monospace",color:"#202124",backgroundColor:"#fff"},children:f})]}),(0,t.jsxs)("div",{style:{border:"1px solid #fce8b2",borderRadius:8,padding:"12px 16px",backgroundColor:"#fefce8",marginBottom:16},children:[(0,t.jsxs)("p",{style:{fontSize:13,color:"#5f6368",lineHeight:1.6,margin:"0 0 8px 0"},children:['If you see "Plugin ',e.name,'not found in marketplace", update the catalog first:']}),(0,t.jsx)("pre",{style:{margin:0,fontSize:13,fontFamily:"monospace",color:"#202124",backgroundColor:"transparent"},children:"/plugin marketplace update litellm"})]}),(0,t.jsxs)("p",{style:{fontSize:13,color:"#5f6368",lineHeight:1.6,margin:0},children:["Don't have the marketplace configured yet?"," ",(0,t.jsx)("span",{onClick:()=>p("setup"),style:{color:"#1a73e8",cursor:"pointer"},children:"See one-time setup →"})]})]}),"setup"===d&&(0,t.jsxs)("div",{style:{maxWidth:640},children:[(0,t.jsx)("h2",{style:{fontSize:18,fontWeight:400,color:"#202124",margin:"0 0 8px 0"},children:"One-time marketplace setup"}),(0,t.jsx)("p",{style:{fontSize:14,color:"#5f6368",margin:"0 0 12px 0",lineHeight:1.6},children:"Run this command in Claude Code to register the marketplace:"}),(0,t.jsxs)("div",{style:{border:"1px solid #dadce0",borderRadius:8,overflow:"hidden",marginBottom:24},children:[(0,t.jsxs)("div",{style:{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"10px 16px",backgroundColor:"#f8f9fa",borderBottom:"1px solid #dadce0"},children:[(0,t.jsx)("span",{style:{fontSize:13,color:"#3c4043",fontWeight:500},children:"Run in Claude Code"}),(0,t.jsxs)("button",{onClick:()=>{let e=window.location.origin;m(`/plugin marketplace add ${e}/claude-code/marketplace.json`,"marketplace-cmd")},style:{display:"flex",alignItems:"center",gap:4,fontSize:12,color:"marketplace-cmd"===u?"#137333":"#1a73e8",background:"none",border:"none",cursor:"pointer",padding:0},children:["marketplace-cmd"===u?(0,t.jsx)(a.Check,{className:"size-3"}):(0,t.jsx)(n.Copy,{className:"size-3"}),"marketplace-cmd"===u?"Copied":"Copy"]})]}),(0,t.jsx)("pre",{style:{margin:0,padding:"14px 16px",fontSize:13,fontFamily:"monospace",color:"#202124",backgroundColor:"#fff"},children:`/plugin marketplace add ${window.location.origin}/claude-code/marketplace.json`})]}),(0,t.jsxs)("p",{style:{fontSize:14,color:"#5f6368",margin:"0 0 12px 0",lineHeight:1.6},children:["Or add this to"," ",(0,t.jsx)("code",{style:{fontSize:13,backgroundColor:"#f1f3f4",padding:"1px 6px",borderRadius:4},children:"~/.claude/settings.json"})," ","for a persistent configuration:"]}),(0,t.jsxs)("div",{style:{border:"1px solid #dadce0",borderRadius:8,overflow:"hidden"},children:[(0,t.jsxs)("div",{style:{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"10px 16px",backgroundColor:"#f8f9fa",borderBottom:"1px solid #dadce0"},children:[(0,t.jsx)("span",{style:{fontSize:13,color:"#3c4043",fontWeight:500},children:"~/.claude/settings.json"}),(0,t.jsxs)("button",{onClick:()=>m(y,"settings"),style:{display:"flex",alignItems:"center",gap:4,fontSize:12,color:"settings"===u?"#137333":"#1a73e8",background:"none",border:"none",cursor:"pointer",padding:0},children:["settings"===u?(0,t.jsx)(a.Check,{className:"size-3"}):(0,t.jsx)(n.Copy,{className:"size-3"}),"settings"===u?"Copied":"Copy"]})]}),(0,t.jsx)("pre",{style:{margin:0,padding:"14px 16px",fontSize:13,fontFamily:"monospace",color:"#202124",backgroundColor:"#fff"},children:y})]})]})]})}],652272)}]);